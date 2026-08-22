import os
import sys
import logging
from datetime import datetime, date, timedelta
import pandas as pd
import numpy as np

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from tvDatafeed import Interval
from src.data.nse_fetcher import fetch_bulk_history, load_nifty100_symbols, load_nifty500_symbols
from src.data.live_tv_fetcher import get_tv_fetcher

from src.screener.pipeline.intraday.config import STRATEGY_CONFIG
from src.screener.pipeline.intraday.features import (
    calculate_gap, calculate_or, calculate_vwap, 
    calculate_time_of_day_rvol, calculate_relative_strength,
    calculate_atr, precompute_historical_rvol, calculate_fast_rvol
)
from src.screener.pipeline.intraday.scoring import compute_signal_score

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class BacktestEngine:
    def __init__(self, config):
        self.config = config
        self.capital = config['starting_capital']
        self.trades = []
        self.equity_curve = []
        
    def calculate_costs(self, entry_price, exit_price, qty, direction):
        """
        Calculate total transaction costs for MIS Equity based on Zerodha/Upstox structure.
        """
        turnover = (entry_price + exit_price) * qty
        
        # Brokerage (0.03% or max Rs 20 per leg)
        brokerage = min((entry_price * qty * self.config['brokerage_pct']), 20) + min((exit_price * qty * self.config['brokerage_pct']), 20)
        
        # STT is only on sell side for intraday equity (0.025%)
        stt = exit_price * qty * self.config['stt_pct'] if direction == "LONG" else entry_price * qty * self.config['stt_pct']
        
        # Exchange txn charge
        exc = turnover * self.config['exchange_txn_charge_pct']
        
        # GST on brokerage + exc (18%)
        gst = (brokerage + exc) * 0.18
        
        # Stamp duty on buy side (0.003%)
        stamp = entry_price * qty * 0.00003 if direction == "LONG" else exit_price * qty * 0.00003
        
        total_cost = brokerage + stt + exc + gst + stamp
        return total_cost
        
    def simulate_day(self, current_date, daily_data, intraday_data, nifty_i, nifty_vwap_df):
        day_trades = []
        
        for sym, i_df in intraday_data.items():
            if sym == "NIFTY": continue
            
            d_df = daily_data.get(sym)
            if d_df is None or i_df.empty: continue
            
            # Historical slices (avoid lookahead)
            d_slice = d_df[d_df.index.date < current_date]
            i_slice = i_df[i_df.index.date <= current_date]
            
            if d_slice.empty or i_slice.empty: continue
            
            today_i_df = i_slice[i_slice.index.date == current_date]
            if today_i_df.empty: continue
            
            # Calculate daily VWAP
            vwap_df = calculate_vwap(i_slice)
            
            # Calculate OR up to 9:30
            or_data = calculate_or(today_i_df, self.config['or_start_time'], self.config['or_end_time'])
            if not or_data: continue
            
            # Precompute historical volume averages for this symbol!
            precomputed_vols = precompute_historical_rvol(i_slice, current_date, self.config['rvol_lookback_days'])
            
            # Find entry (first 5m candle closing beyond OR after OR ends)
            after_or_df = today_i_df.between_time(self.config['entry_start'], self.config['entry_end'])
            
            for t_idx, row in after_or_df.iterrows():
                current_time = t_idx.strftime('%H:%M')
                
                # Check metrics precisely at t_idx
                i_df_t = today_i_df.loc[:t_idx]
                nifty_up_to_t = nifty_i.loc[:t_idx]
                
                if nifty_up_to_t.empty: continue
                
                rvol, _, _ = calculate_fast_rvol(i_df_t, current_time, precomputed_vols)
                gap_pct, _ = calculate_gap(d_slice, today_i_df['Open'].iloc[0])
                rs = calculate_relative_strength(today_i_df.loc[:t_idx], nifty_up_to_t[nifty_up_to_t.index.date == current_date])
                
                features = {
                    "current_price": row['Close'],
                    "gap_pct": gap_pct,
                    "orh": or_data['orh'],
                    "orl": or_data['orl'],
                    "or_width_pct": or_data['or_width_pct'],
                    "rvol": rvol,
                    "vwap": vwap_df['VWAP'].loc[t_idx],
                    "vwap_slope": vwap_df['VWAP_Slope'].loc[t_idx],
                    "breakout_vol_ratio": 1.5, # Simplified for backtest speed, actual logic needs historical avg calc per row
                    "relative_strength": rs,
                    "nifty_price": nifty_up_to_t['Close'].iloc[-1],
                    "nifty_vwap": nifty_vwap_df['VWAP'].loc[t_idx],
                    "rr": 2.0
                }
                
                # Trigger condition
                direction = None
                if row['Close'] > or_data['orh']:
                    direction = "LONG"
                elif row['Close'] < or_data['orl']:
                    direction = "SHORT"
                    
                if not direction: continue
                
                score, _ = compute_signal_score(self.config, features, direction)
                
                if score >= self.config.get('min_score', 10): # Minimum score to trade
                    # Execute Trade!
                    slippage = row['Close'] * self.config['slippage_pct']
                    entry_price = row['Close'] + slippage if direction == "LONG" else row['Close'] - slippage
                    
                    atr = calculate_atr(d_slice, period=14)
                    if atr <= 0: continue
                    
                    if direction == "LONG":
                        sl = entry_price - (atr * self.config['atr_multiplier'])
                        risk_per_share = entry_price - sl
                    else:
                        sl = entry_price + (atr * self.config['atr_multiplier'])
                        risk_per_share = sl - entry_price
                        
                    if risk_per_share <= 0: continue
                        
                    # Position sizing
                    max_risk = self.capital * self.config['risk_per_trade_pct']
                    desired_qty = int(max_risk / risk_per_share)
                    
                    # Cap quantity to 5x MIS Intraday Leverage limit
                    max_allowed_position_value = self.capital * 5.0
                    max_allowed_qty = int(max_allowed_position_value / entry_price)
                    
                    qty = min(desired_qty, max_allowed_qty)
                    
                    if qty == 0: continue
                    
                    target = entry_price + (risk_per_share * self.config['target_r_multiple']) if direction == "LONG" else entry_price - (risk_per_share * self.config['target_r_multiple'])
                    
                    # Manage Trade through rest of day
                    trade_df = today_i_df.loc[t_idx:]
                    exit_price = 0
                    exit_type = "TIME_EXIT"
                    
                    for _, t_row in trade_df.iterrows():
                        if direction == "LONG":
                            if t_row['High'] >= target:
                                exit_price = target
                                exit_type = "TARGET"
                                break
                            if t_row['Low'] <= sl:
                                exit_price = sl
                                exit_type = "STOP_LOSS"
                                break
                        else:
                            if t_row['Low'] <= target:
                                exit_price = target
                                exit_type = "TARGET"
                                break
                            if t_row['High'] >= sl:
                                exit_price = sl
                                exit_type = "STOP_LOSS"
                                break
                                
                    if exit_price == 0:
                        exit_price = trade_df['Close'].iloc[-1]
                        
                    # Slippage on exit
                    exit_price = exit_price - slippage if direction == "LONG" else exit_price + slippage
                        
                    gross_pnl = (exit_price - entry_price) * qty if direction == "LONG" else (entry_price - exit_price) * qty
                    costs = self.calculate_costs(entry_price, exit_price, qty, direction)
                    net_pnl = gross_pnl - costs
                    
                    day_trades.append({
                        "Date": current_date,
                        "Symbol": sym,
                        "Direction": direction,
                        "Score": score,
                        "Entry_Time": t_idx.strftime('%H:%M'),
                        "Entry": entry_price,
                        "SL": sl,
                        "Target": target,
                        "Exit": exit_price,
                        "Exit_Type": exit_type,
                        "Qty": qty,
                        "Gross_PnL": gross_pnl,
                        "Costs": costs,
                        "Net_PnL": net_pnl
                    })
                    
                    # Only 1 trade per stock per day for simplicity
                    break
        
        return day_trades

    def run(self):
        logger.info("Initializing Backtest Engine...")
        symbols = load_nifty100_symbols()
        
        logger.info("Fetching EOD daily data...")
        daily_data = fetch_bulk_history(symbols + ["NIFTY"], end_date=date.today(), lookback_days=100)
        
        CACHE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "bhavcopy_cache", "intraday_5m")
        os.makedirs(CACHE_DIR, exist_ok=True)
        
        logger.info("Loading/Caching 5m intraday data (Takes time if not cached)...")
        intraday_data = {}
        fetcher = get_tv_fetcher()
        n_bars = 4000 
        
        for sym in (symbols + ["NIFTY"]):
            cache_path = os.path.join(CACHE_DIR, f"{sym}_5m.parquet")
            if os.path.exists(cache_path):
                try:
                    df = pd.read_parquet(cache_path)
                    if not df.empty:
                        intraday_data[sym] = df
                        continue
                except Exception as e:
                    logger.debug(f"Error reading cache for {sym}: {e}")
            
            # Fetch if not cached
            try:
                df = fetcher.fetch_symbol_intraday(sym, interval=Interval.in_5_minute, n_bars=n_bars)
                if df is not None and not df.empty:
                    df.to_parquet(cache_path)
                    intraday_data[sym] = df
            except Exception as e:
                logger.debug(f"Failed to fetch {sym}: {e}")
        
        nifty_i = intraday_data.get("NIFTY")
        if nifty_i is None or nifty_i.empty:
            logger.error("No NIFTY data.")
            return
            
        nifty_vwap_df = calculate_vwap(nifty_i)
        
        unique_dates = pd.Series(nifty_i.index.date).unique()
        # Skip first 20 days to allow for RVOL lookback
        valid_dates = unique_dates[20:]
        
        logger.info(f"Running simulation over {len(valid_dates)} trading days...")
        
        all_trades = []
        for d in valid_dates:
            day_trades = self.simulate_day(d, daily_data, intraday_data, nifty_i, nifty_vwap_df)
            
            # Sort by score and take max trades per day
            day_trades = sorted(day_trades, key=lambda x: x['Score'], reverse=True)
            day_trades = day_trades[:self.config['max_trades_per_day']]
            
            for t in day_trades:
                self.capital += t['Net_PnL']
                
            self.equity_curve.append({
                "Date": d,
                "Capital": self.capital,
                "Daily_PnL": sum(t['Net_PnL'] for t in day_trades)
            })
            all_trades.extend(day_trades)
            
        self.trades = all_trades
        self.generate_report()
        
    def generate_report(self):
        df = pd.DataFrame(self.trades)
        if df.empty:
            logger.info("No trades generated during backtest!")
            return
            
        wins = df[df['Net_PnL'] > 0]
        losses = df[df['Net_PnL'] <= 0]
        
        win_rate = len(wins) / len(df) * 100
        total_net_pnl = df['Net_PnL'].sum()
        total_costs = df['Costs'].sum()
        
        logger.info("=== BACKTEST RESULTS ===")
        logger.info(f"Total Trades: {len(df)}")
        logger.info(f"Win Rate: {win_rate:.2f}%")
        logger.info(f"Total Net PnL: Rs {total_net_pnl:.2f}")
        logger.info(f"Total Transaction Costs Paid: Rs {total_costs:.2f}")
        logger.info(f"Final Capital: Rs {self.capital:.2f}")
        
        df.to_csv("backtest_results.csv", index=False)
        
if __name__ == "__main__":
    engine = BacktestEngine(STRATEGY_CONFIG)
    engine.run()
