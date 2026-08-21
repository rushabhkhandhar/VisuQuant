import os
import sys
import logging
import pandas as pd
from datetime import datetime

# Add the project root to sys.path (since we are in fno/ directory now)
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.data.nse_fetcher import load_fno_symbols
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.swing.compare_strategies import STRATEGIES
from src.screener.pipeline.swing.run_front_test import load_state, STATE_FILE
import json

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Filter down to the 3 proven strategies we want to run live
LIVE_STRATEGY_NAMES = ["Momentum Breakout", "Relative Strength", "Volatility Compression"]
LIVE_STRATEGIES = [s for s in STRATEGIES if s["name"] in LIVE_STRATEGY_NAMES]

def get_live_market_regime(nifty_hist):
    if nifty_hist is not None and not nifty_hist.empty and len(nifty_hist) >= 60:
        sma_50 = nifty_hist["Close"].rolling(50).mean()
        sma_50_diff = sma_50.diff()
        
        curr_close = nifty_hist["Close"].iloc[-1]
        curr_sma50 = sma_50.iloc[-1]
        curr_sma50_diff = sma_50_diff.iloc[-1]
        
        if curr_close > curr_sma50 and curr_sma50_diff > 0:
            return "Bullish"
        elif curr_close < curr_sma50 and curr_sma50_diff < 0:
            return "Bearish"
        else:
            return "Choppy"
    return "Unknown"

def check_open_trades_live(trades, bulk_data):
    """Check if open trades hit their target or stop loss based on live data."""
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    closed_trades = []
    
    if not open_trades:
        return closed_trades
        
    for t in open_trades:
        sym = t["symbol"]
        if sym in bulk_data:
            df = bulk_data[sym]
            live_low = df['Low'].iloc[-1]
            live_high = df['High'].iloc[-1]
            live_close = df['Close'].iloc[-1]
            
            if live_low <= t["stop_loss"]:
                closed_trades.append({
                    "symbol": sym,
                    "strategy": t["strategy_name"],
                    "action": "SELL (STOP LOSS)",
                    "price": live_close,
                    "pnl": ((live_close - t["entry_price"]) / t["entry_price"]) * 100
                })
            elif live_high >= t["target"]:
                closed_trades.append({
                    "symbol": sym,
                    "strategy": t["strategy_name"],
                    "action": "SELL (TARGET)",
                    "price": live_close,
                    "pnl": ((live_close - t["entry_price"]) / t["entry_price"]) * 100
                })
                
    return closed_trades

def run_live_strategies(bulk_data, nifty_hist):
    """Run the strategy evaluations on the live bulk data."""
    new_signals = []
    
    # We do not have sector_hist in the live feed for simplicity, we pass None
    # Our relative strength uses nifty_hist fallback anyway.
    
    for strategy in LIVE_STRATEGIES:
        logger.info(f"Evaluating {strategy['name']} on live data...")
        eval_func = strategy["func"]
        
        for symbol, df in bulk_data.items():
            if len(df) < 200:
                continue
                
            try:
                res = eval_func(df, nifty_hist=nifty_hist, sector_hist=None)
                if res and res.get("passed", False):
                    live_close = df['Close'].iloc[-1]
                    new_signals.append({
                        "symbol": symbol,
                        "strategy": strategy["name"],
                        "action": "BUY",
                        "price": live_close
                    })
            except Exception as e:
                # logger.debug(f"Error evaluating {symbol} for {strategy['name']}: {e}")
                pass
                
    # Build Live Ensemble Strategy
    symbol_counts = {}
    for signal in new_signals:
        if signal["action"] == "BUY":
            symbol = signal["symbol"]
            if symbol not in symbol_counts:
                symbol_counts[symbol] = []
            symbol_counts[symbol].append(signal)
            
    for symbol, signals in symbol_counts.items():
        if len(signals) >= 2:
            # Create an ensemble buy signal
            price = signals[0]["price"]
            strategy_names = [s["strategy"] for s in signals]
            new_signals.append({
                "symbol": symbol,
                "strategy": "Ensemble Strategy",
                "action": "BUY",
                "price": price,
                "note": f"Passed {len(signals)}: {', '.join(strategy_names)}"
            })
            
    return new_signals

def print_terminal_table(title, items):
    print(f"\n{'='*70}")
    print(f"{title.upper().center(70)}")
    print(f"{'='*70}")
    if not items:
        print("No signals found.")
        print(f"{'='*70}\n")
        return
        
    print(f"{'SYMBOL':<15} | {'ACTION':<20} | {'PRICE':<10} | {'STRATEGY / PNL'}")
    print("-" * 70)
    for item in items:
        action = item["action"]
        price = f"{item['price']:.2f}"
        
        if "BUY" in action:
            extra = item.get("note", item["strategy"])
        else:
            extra = f"{item['strategy']} ({item['pnl']:.2f}%)"
            
        print(f"{item['symbol']:<15} | {action:<20} | {price:<10} | {extra}")
    print(f"{'='*70}\n")

def main():
    print("\n" + "*"*70)
    print("LIVE MARKET SCREENER (3:15 PM MOC EXECUTION)".center(70))
    print("*"*70 + "\n")
    
    logger.info("Loading F&O universe...")
    symbols = load_fno_symbols()
    
    # Also fetch NIFTYBEES for benchmark
    symbols.append("NIFTYBEES")
    
    fetcher = get_tv_fetcher()
    bulk_data = fetcher.fetch_bulk_live(symbols, n_bars=220, max_workers=10)
    
    if "NIFTYBEES" not in bulk_data:
        logger.error("Failed to fetch NIFTYBEES for benchmark. Exiting.")
        return
        
    nifty_hist = bulk_data.pop("NIFTYBEES")
    regime = get_live_market_regime(nifty_hist)
    print(f"\n>>> CURRENT MARKET REGIME: {regime} <<<\n")
    
    logger.info("Checking existing open trades...")
    trades = load_state()
    closed_signals = check_open_trades_live(trades, bulk_data)
    
    logger.info("Scanning for new BUY signals...")
    buy_signals = run_live_strategies(bulk_data, nifty_hist)
    
    # We do NOT save state here. State is managed by the EOD backtester/tracker.
    # This script is purely for generating live execution signals for the user.
    
    print_terminal_table("SELL SIGNALS (STOP / TARGET HIT)", closed_signals)
    print_terminal_table("BUY SIGNALS (NEW BREAKOUTS)", buy_signals)
    
if __name__ == "__main__":
    main()
