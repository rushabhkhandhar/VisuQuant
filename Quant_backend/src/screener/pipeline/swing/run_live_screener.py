import os
import sys
import logging
import pandas as pd
from datetime import datetime

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.data.nse_fetcher import load_nifty500_symbols
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.swing.compare_strategies import STRATEGIES
from src.screener.pipeline.swing.run_front_test import (
    load_state, STATE_FILE, record_live_signals, save_state,
    relative_strength_eval, momentum_breakout_eval, oversold_uptrend_eval, trend_pullback_eval,
)
from src.screener.pipeline.swing.e12_strategy import generate_e12_signals
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

def compute_live_bcr(bulk_data, lookback_days=120, outcome_days=20, min_gap_days=30):
    """
    Breakout Continuation Rate: % of 40-day-high breakouts (from lookback_days→min_gap_days ago)
    that were higher outcome_days later.
    Uses ONLY historical data — no forward bias.
    Returns float in [0,1]. Default 0.5 (neutral) if insufficient data.
    """
    from datetime import datetime, timedelta
    cutoff_end = pd.Timestamp.today() - pd.Timedelta(days=min_gap_days)
    cutoff_start = pd.Timestamp.today() - pd.Timedelta(days=lookback_days + outcome_days)
    
    continued = []
    for sym, df in bulk_data.items():
        if len(df) < 60:
            continue
        high_40 = df['High'].rolling(40).max().shift(1)
        mask = (df.index >= cutoff_start) & (df.index <= cutoff_end)
        for idx in df.index[mask]:
            pos = df.index.get_loc(idx)
            if pos + outcome_days >= len(df):
                continue
            if pd.notna(high_40.iloc[pos]) and df['Close'].iloc[pos] > high_40.iloc[pos]:
                entry_p = df['Close'].iloc[pos]
                future_p = df['Close'].iloc[pos + outcome_days]
                continued.append(1 if future_p > entry_p else 0)
    
    if len(continued) < 10:
        return 0.5  # neutral — not enough data
    return sum(continued) / len(continued)


def compute_live_breadth(bulk_data):
    """
    Market breadth: fraction of stocks with Close > 50-day SMA today.
    Purely historical — uses only current bar data. No forward bias.
    """
    above = 0
    total = 0
    for sym, df in bulk_data.items():
        if len(df) < 50:
            continue
        sma50 = df['Close'].rolling(50).mean().iloc[-1]
        close = df['Close'].iloc[-1]
        if pd.notna(sma50):
            total += 1
            if close > sma50:
                above += 1
    return above / total if total > 0 else 0.5


def run_live_strategies(bulk_data, nifty_hist):
    """
    E11_Three_State regime-adaptive architecture (mirrors compare_strategies.py E11).
    
    STATE 1 — TREND (BCR > 52%):         RS Alpha + Momentum Confirmation
    STATE 2 — MEAN-REVERT (BCR ≤ 52%, breadth ≥ 30%): Oversold Uptrend + Trend Pullback
    STATE 3 — CASH (BCR ≤ 52%, breadth < 30%):  No new signals
    
    All regime inputs are backward-looking only. No forward bias.
    """
    # The canonical generator is also used by the forward-test ledger and the
    # historical comparator.  Do not add live-only filters here.
    from src.data.nse_fetcher import load_nifty500_industry_mapping
    return generate_e12_signals(
        bulk_data=bulk_data,
        nifty_hist=nifty_hist,
        as_of_date=pd.Timestamp.now(),
        industry_mapping=load_nifty500_industry_mapping(),
        evaluators={
            "relative_strength": relative_strength_eval,
            "momentum_breakout": momentum_breakout_eval,
            "oversold_uptrend": oversold_uptrend_eval,
            "trend_pullback": trend_pullback_eval,
        },
    )

    import talib
    
    BCR_THRESHOLD = 0.52   # Principled: momentum must beat a coin flip
    BREADTH_THRESHOLD = 0.30  # Principled: <30% stocks above SMA50 = extreme weakness
    
    # --- Compute live regime indicators ---
    bcr = compute_live_bcr(bulk_data)
    breadth = compute_live_breadth(bulk_data)
    
    if bcr > BCR_THRESHOLD:
        regime_state = 1
        regime_label = f"TREND-PERSISTENT (BCR={bcr:.3f} > {BCR_THRESHOLD}) → Momentum Signals"
    elif breadth < BREADTH_THRESHOLD:
        regime_state = 3
        regime_label = f"CASH PRESERVATION (BCR={bcr:.3f} ≤ {BCR_THRESHOLD}, Breadth={breadth:.1%} < {BREADTH_THRESHOLD:.0%}) → No New Entries"
    else:
        regime_state = 2
        regime_label = f"MEAN-REVERTING (BCR={bcr:.3f} ≤ {BCR_THRESHOLD}, Breadth={breadth:.1%} ≥ {BREADTH_THRESHOLD:.0%}) → Oversold Signals"
    
    print(f"\n>>> E11 REGIME STATE {regime_state}: {regime_label}\n")
    logger.info(f"Live BCR={bcr:.3f}, Breadth={breadth:.1%}, Regime State={regime_state}")
    
    if regime_state == 3:
        logger.info("CASH PRESERVATION mode — no new signals generated.")
        return []
    
    # --- Build sector indices ---
    from src.data.nse_fetcher import load_nifty500_industry_mapping
    from src.screener.pipeline.swing.run_front_test import (
        relative_strength_eval, momentum_breakout_eval,
        oversold_uptrend_eval, trend_pullback_eval
    )
    industry_mapping = load_nifty500_industry_mapping()
    sector_indices = {}
    sectors = {}
    for sym, df in bulk_data.items():
        if sym in industry_mapping and not df.empty:
            ind = industry_mapping[sym]
            if ind not in sectors:
                sectors[ind] = []
            sectors[ind].append(df['Close'].pct_change().fillna(0))
    for ind, returns_list in sectors.items():
        avg_returns = pd.concat(returns_list, axis=1).mean(axis=1)
        synthetic_price = 100 * (1 + avg_returns).cumprod()
        sector_indices[ind] = pd.DataFrame({"Close": synthetic_price})
    
    # --- Assign primary/confirmation by regime state ---
    if regime_state == 1:
        primary_func = relative_strength_eval
        confirm_func = momentum_breakout_eval
        signal_prefix = "Trend"
    else:  # state 2
        primary_func = oversold_uptrend_eval
        confirm_func = trend_pullback_eval
        signal_prefix = "MeanRev"
    
    logger.info(f"Scanning universe with State {regime_state} signals...")
    new_signals = []
    
    for symbol, df in bulk_data.items():
        if len(df) < 200:
            continue
        try:
            sector_hist = None
            if symbol in industry_mapping:
                ind = industry_mapping[symbol]
                if ind in sector_indices:
                    sector_hist = sector_indices[ind]
            
            p_res = primary_func(df, nifty_hist=nifty_hist, sector_hist=sector_hist)
            if not p_res or not p_res.get('passed'):
                continue
            
            try:
                c_res = confirm_func(df, nifty_hist=nifty_hist, sector_hist=sector_hist)
            except:
                c_res = None
            
            confirmed = c_res and c_res.get('passed')
            risk_pct = 0.025 if confirmed else 0.01
            signal_type = f"{signal_prefix}: {'CONFIRMED' if confirmed else 'Primary Only'}"
            
            live_close = df['Close'].iloc[-1]
            atr = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
            
            if pd.notna(atr) and atr > 0:
                alpha_score = p_res.get('alpha_score', 0.0)
                stop_loss = live_close - (atr * 2.0)
                target = live_close + (atr * 4.0)
                
                new_signals.append({
                    "symbol": symbol,
                    "strategy": signal_type,
                    "action": "BUY",
                    "price": live_close,
                    "stop_loss": round(stop_loss, 2),
                    "target": round(target, 2),
                    "risk_pct": risk_pct,
                    "alpha_score": round(alpha_score, 4),
                    "regime_state": regime_state,
                    "note": f"BCR={bcr:.3f} | Breadth={breadth:.1%} | Alpha={alpha_score:.4f} | Risk={risk_pct*100:.1f}%"
                })
        except Exception:
            pass
    
    # Rank by alpha score (highest first) — best conviction signals first
    new_signals.sort(key=lambda x: x.get('alpha_score', 0.0), reverse=True)
    return new_signals

def print_terminal_table(title, items):
    print(f"\n{'='*90}")
    print(f"{title.upper().center(90)}")
    print(f"{'='*90}")
    if not items:
        print("No signals found.")
        print(f"{'='*90}\n")
        return
    
    if "BUY" in (items[0].get("action", "") if items else ""):
        print(f"{'#':<4} {'SYMBOL':<15} {'ALPHA':<10} {'PRICE':<10} {'SL':<10} {'TGT':<10} {'CONVICTION'}")
        print("-" * 90)
        for i, item in enumerate(items, 1):
            alpha = f"{item.get('alpha_score', 0):.4f}"
            price = f"{item['price']:.2f}"
            sl = f"{item.get('stop_loss', '-')}"
            tgt = f"{item.get('target', '-')}"
            strategy = item.get("strategy", "")
            print(f"{i:<4} {item['symbol']:<15} {alpha:<10} {price:<10} {sl:<10} {tgt:<10} {strategy}")
    else:
        print(f"{'SYMBOL':<15} | {'ACTION':<20} | {'PRICE':<10} | {'STRATEGY / PNL'}")
        print("-" * 90)
        for item in items:
            action = item["action"]
            price = f"{item['price']:.2f}"
            extra = f"{item['strategy']} ({item['pnl']:.2f}%)"
            print(f"{item['symbol']:<15} | {action:<20} | {price:<10} | {extra}")
    print(f"{'='*90}\n")

def main():
    print("\n" + "*"*70)
    print("LIVE MARKET SCREENER (3:15 PM MOC EXECUTION)".center(70))
    print("*"*70 + "\n")
    
    logger.info("Loading NIFTY 500 universe...")
    symbols = load_nifty500_symbols()
    
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

    # Persist the exact 3:15 PM candidates.  The EOD process is a ledger: it
    # updates these records, it must not independently rescan final-close data.
    trades = record_live_signals(trades, buy_signals, datetime.now())
    save_state(trades)
    
    # We do NOT save state here. State is managed by the EOD backtester/tracker.
    # This script is purely for generating live execution signals for the user.
    
    print_terminal_table("SELL SIGNALS (STOP / TARGET HIT)", closed_signals)
    print_terminal_table("BUY SIGNALS (NEW BREAKOUTS)", buy_signals)
    
if __name__ == "__main__":
    main()
