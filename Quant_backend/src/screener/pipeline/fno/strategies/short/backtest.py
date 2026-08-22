import os
import sys
import logging
from datetime import date
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))))

from tvDatafeed import Interval
from src.data.nse_fetcher import fetch_bulk_history, load_fno_symbols, load_nifty500_industry_mapping
from src.data.live_tv_fetcher import get_tv_fetcher
from src.screener.pipeline.fno.strategies.short.config import STRATEGY_CONFIG
from src.screener.pipeline.fno.strategies.short.screener import FnoShortScreener
from src.screener.pipeline.intraday.features import calculate_atr

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')
logger = logging.getLogger(__name__)

class FnoShortBacktest:
    def __init__(self, config):
        self.config = config
        self.capital = config['starting_capital']
        self.trades = []
        self.screener = FnoShortScreener(config)
        self.tv = get_tv_fetcher()
        
    def get_futures_data(self, symbols, end_date, lookback_days=100):
        """Fetch continuous front-month futures data (SYMBOL1!) using tvDatafeed."""
        CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))), "bhavcopy_cache", "futures_daily")
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        futures_data = {}
        for sym in symbols:
            fut_sym = f"{sym}1!"
            cache_path = os.path.join(CACHE_DIR, f"{sym}_fut.parquet")
            missing_path = os.path.join(CACHE_DIR, f"{sym}_fut.missing")
            
            if os.path.exists(missing_path):
                continue
                
            if os.path.exists(cache_path):
                try:
                    df = pd.read_parquet(cache_path)
                    if not df.empty:
                        futures_data[sym] = df
                        continue
                except: pass
                
            try:
                # Fetch 200 daily bars to ensure we have enough lookback
                df = self.tv.fetch_symbol_intraday(fut_sym, interval=Interval.in_daily, n_bars=200)
                if df is not None and not df.empty:
                    df.to_parquet(cache_path)
                    futures_data[sym] = df
                else:
                    with open(missing_path, 'w') as f: f.write("")
            except Exception as e:
                logger.debug(f"Failed to fetch {fut_sym}: {e}")
                with open(missing_path, 'w') as f: f.write("")
                
        return futures_data

    def run(self):
        logger.info("Initializing F&O Swing Short Backtest...")
        symbols = load_fno_symbols()
        ind_map = load_nifty500_industry_mapping()
        
        logger.info("Fetching static Cash EOD data for Screener logic...")
        cash_data = fetch_bulk_history(symbols + ["NIFTY"], end_date=date.today(), lookback_days=150)
        
        logger.info("Fetching Continuous Futures data for execution...")
        futures_data = self.get_futures_data(symbols, end_date=date.today())
        
        if not futures_data:
            logger.error("No futures data downloaded.")
            return
            
        # Get common trading days based on the first successfully fetched stock
        first_symbol = list(cash_data.keys())[0]
        ref_df = cash_data.get(first_symbol)
        trading_days = pd.Series(ref_df.index.date).unique()[30:] # Skip first 30 days for lookback
        
        logger.info(f"Running simulation over {len(trading_days)} days...")
        
        open_positions = []
        
        for current_date in trading_days:
            # 1. Manage open positions
            remaining_positions = []
            for pos in open_positions:
                sym = pos['symbol']
                fut_df = futures_data.get(sym)
                if fut_df is None: continue
                
                # Get today's futures candle
                today_fut = fut_df[fut_df.index.date == current_date]
                if today_fut.empty: 
                    remaining_positions.append(pos)
                    continue
                    
                t_row = today_fut.iloc[0]
                exit_price = 0
                exit_type = ""
                
                # Check for stop loss or target (assume SL hit first if both hit in same day for conservative backtest)
                if t_row['High'] >= pos['sl']:
                    exit_price = pos['sl']
                    exit_type = "STOP_LOSS"
                elif t_row['Low'] <= pos['target']:
                    exit_price = pos['target']
                    exit_type = "TARGET"
                    
                if exit_price > 0:
                    # Execute Exit
                    gross_pnl = (pos['entry_price'] - exit_price) * pos['qty']
                    
                    # Estimate costs (Futures STT on sell, brokerages)
                    turnover = (pos['entry_price'] + exit_price) * pos['qty']
                    stt = pos['entry_price'] * pos['qty'] * 0.000125 # STT on sell side for futures
                    costs = (turnover * 0.00002) + stt + 40 # Exchange + Brokerage max
                    
                    net_pnl = gross_pnl - costs
                    self.capital += net_pnl
                    
                    self.trades.append({
                        "Date_Entry": pos['entry_date'],
                        "Date_Exit": current_date,
                        "Symbol": sym,
                        "Entry": pos['entry_price'],
                        "Exit": exit_price,
                        "Qty": pos['qty'],
                        "Net_PnL": net_pnl,
                        "Type": exit_type
                    })
                else:
                    remaining_positions.append(pos)
                    
            open_positions = remaining_positions
            
            # 2. Find new setups if we have room
            slots_available = self.config['max_open_positions'] - len(open_positions)
            if slots_available > 0:
                picks = self.screener.screen(current_date, cash_data, ind_map)
                
                for sym in picks:
                    if slots_available == 0: break
                    # Don't double down
                    if any(p['symbol'] == sym for p in open_positions): continue
                    
                    # Execute entry on Futures
                    fut_df = futures_data.get(sym)
                    if fut_df is None: continue
                    
                    slice_fut = fut_df[fut_df.index.date <= current_date]
                    if slice_fut.empty: continue
                    
                    # Assume entry at Close price (3:15 PM proxy)
                    entry_price = slice_fut['Close'].iloc[-1]
                    
                    # Calculate ATR on Cash data for Stop Loss (since cash data has longer history in our cache)
                    cash_slice = cash_data[sym][cash_data[sym].index.date <= current_date]
                    atr = calculate_atr(cash_slice, period=self.config['atr_period'])
                    if atr == 0: continue
                    
                    sl = entry_price + (atr * self.config['atr_stop_loss_multiplier'])
                    risk_per_share = sl - entry_price
                    if risk_per_share <= 0: continue
                    
                    # Position Sizing
                    max_risk = self.capital * self.config['risk_per_trade_pct']
                    desired_qty = int(max_risk / risk_per_share)
                    
                    # Lot size mocking (approx Rs 7,000,000 per lot value in F&O)
                    # A stock at Rs 1000 usually has a lot size of ~700
                    lot_size = max(1, int(700000 / entry_price))
                    
                    # Round down to nearest lot
                    lots = int(desired_qty / lot_size)
                    if lots == 0: continue # Risk doesn't allow even 1 lot
                    
                    qty = lots * lot_size
                    
                    # Check Margin (Require ~20% of contract value)
                    contract_value = qty * entry_price
                    required_margin = contract_value * self.config['margin_requirement_pct']
                    if required_margin > self.capital:
                        # Cannot afford margin
                        continue
                        
                    target = entry_price - (risk_per_share * self.config['target_r_multiple'])
                    
                    open_positions.append({
                        "symbol": sym,
                        "entry_date": current_date,
                        "entry_price": entry_price,
                        "qty": qty,
                        "sl": sl,
                        "target": target
                    })
                    slots_available -= 1
                    
        self.generate_report()
        
    def generate_report(self):
        df = pd.DataFrame(self.trades)
        if df.empty:
            logger.info("No trades generated during backtest!")
            return
            
        win_rate = (df['Net_PnL'] > 0).mean() * 100
        logger.info("\n=== F&O SHORT STRATEGY RESULTS ===")
        logger.info(f"Total Trades: {len(df)}")
        logger.info(f"Win Rate: {win_rate:.2f}%")
        logger.info(f"Total Net PnL: Rs {df['Net_PnL'].sum():.2f}")
        logger.info(f"Final Capital: Rs {self.capital:.2f}")
        
        df.to_csv("fno_short_results.csv", index=False)

if __name__ == "__main__":
    engine = FnoShortBacktest(STRATEGY_CONFIG)
    engine.run()
