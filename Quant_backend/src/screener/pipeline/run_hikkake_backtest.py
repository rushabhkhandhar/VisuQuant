## breakout ka liye hai 

import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import date, datetime, timedelta

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

BACKTEST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    "backtesting"
)
os.makedirs(BACKTEST_DIR, exist_ok=True)
CSV_LOG_PATH = os.path.join(BACKTEST_DIR, "hikkake_trials.csv")

def evaluate_hikkake(df):
    """
    Evaluates the dataframe for the Inside Bar Fakeout (Hikkake) pattern.
    Adds boolean columns 'Cond1_Buy' and 'Cond2_Sell'.
    """
    df = df.copy()
    
    # Pre-calculate shifted values for vectorized conditions
    # d0 = current row, d1 = 1 day ago, d2 = 2 days ago
    
    d1_high = df['High'].shift(1)
    d1_low = df['Low'].shift(1)
    
    d2_open = df['Open'].shift(2)
    d2_close = df['Close'].shift(2)
    d2_high = df['High'].shift(2)
    d2_low = df['Low'].shift(2)
    
    # Condition 1: Bullish Fakeout
    c1_d2_green = d2_open < d2_close
    c1_d2_body_size = (d2_close - d2_open).abs()
    c1_d2_range = (d2_high - d2_low).abs()
    c1_d2_strong = c1_d2_body_size > (c1_d2_range * 0.6)
    
    c1_d1_inside = (d1_high <= d2_high) & (d1_low >= d2_low)
    
    c1_d0_breakdown = (df['Low'] < d1_low) & (df['High'] < d1_high)
    c1_d0_reject = df['Close'] > d1_low
    
    df['Cond1_Buy'] = c1_d2_green & c1_d2_strong & c1_d1_inside & c1_d0_breakdown & c1_d0_reject
    
    # Condition 2: Bearish Fakeout
    c2_d2_red = d2_open > d2_close
    c2_d2_body_size = (d2_open - d2_close).abs()
    c2_d2_range = (d2_high - d2_low).abs()
    c2_d2_strong = c2_d2_body_size > (c2_d2_range * 0.6)
    
    c2_d1_inside = (d1_high < d2_high) & (d1_low > d2_low)
    
    c2_d0_breakout = (df['High'] > d1_high) & (df['Low'] > d1_low)
    c2_d0_reject = df['Close'] < d1_high
    
    df['Cond2_Sell'] = c2_d2_red & c2_d2_strong & c2_d1_inside & c2_d0_breakout & c2_d0_reject
    
    return df

def simulate_trades(df, symbol):
    """
    Simulates trades based on Cond1_Buy and Cond2_Sell signals.
    We track the performance over 5 days and 10 days.
    """
    trades = []
    signals = df[(df['Cond1_Buy'] == True) | (df['Cond2_Sell'] == True)]
    
    for idx, row in signals.iterrows():
        signal_date = idx
        idx_loc = df.index.get_loc(signal_date)
        
        # Ensure we have future data to evaluate
        if idx_loc >= len(df) - 1:
            continue 
            
        entry_price = row['Close'] # Entering on Close of Day 0
        cond_type = "Bullish Fakeout" if row['Cond1_Buy'] else "Bearish Fakeout"
        action = "BUY" if row['Cond1_Buy'] else "SHORT"
        
        # Track forward performance (Max High, Min Low, Close after N days)
        fwd_5d = df.iloc[idx_loc+1 : min(idx_loc+6, len(df))]
        fwd_10d = df.iloc[idx_loc+1 : min(idx_loc+11, len(df))]
        
        if len(fwd_5d) > 0:
            max_5d = fwd_5d['High'].max()
            min_5d = fwd_5d['Low'].min()
            close_5d = fwd_5d['Close'].iloc[-1]
        else:
            continue
            
        if len(fwd_10d) > 0:
            max_10d = fwd_10d['High'].max()
            min_10d = fwd_10d['Low'].min()
            close_10d = fwd_10d['Close'].iloc[-1]
        else:
            max_10d = max_5d
            min_10d = min_5d
            close_10d = close_5d
            
        # PnL calculations
        if action == "BUY":
            pnl_5d = ((close_5d - entry_price) / entry_price) * 100
            pnl_10d = ((close_10d - entry_price) / entry_price) * 100
            max_profit_10d = ((max_10d - entry_price) / entry_price) * 100
            max_drawdown_10d = ((min_10d - entry_price) / entry_price) * 100
        else: # SHORT
            pnl_5d = ((entry_price - close_5d) / entry_price) * 100
            pnl_10d = ((entry_price - close_10d) / entry_price) * 100
            max_profit_10d = ((entry_price - min_10d) / entry_price) * 100
            max_drawdown_10d = ((entry_price - max_10d) / entry_price) * 100

        trades.append({
            "Symbol": symbol,
            "Signal_Date": signal_date.strftime("%Y-%m-%d"),
            "Condition": cond_type,
            "Action": action,
            "Entry_Price": round(entry_price, 2),
            "Close_5d": round(close_5d, 2),
            "PnL_5d_%": round(pnl_5d, 2),
            "Close_10d": round(close_10d, 2),
            "PnL_10d_%": round(pnl_10d, 2),
            "Max_Profit_10d_%": round(max_profit_10d, 2),
            "Max_Drawdown_10d_%": round(max_drawdown_10d, 2)
        })
        
    return trades

def main():
    logger.info("Starting Hikkake Backtest Engine (2 Years)...")
    
    symbols = load_nifty500_symbols()
    logger.info(f"Loaded {len(symbols)} symbols from NIFTY 500.")
    
    # 2 years = roughly 500 trading days. Let's fetch 600 calendar days to be safe
    logger.info("Fetching bulk historical data from NSE (Bypassing TradingView)...")
    bulk_data = fetch_bulk_history(symbols, end_date=date.today(), lookback_days=700)
    
    if not bulk_data:
        logger.error("Failed to fetch historical data. Exiting.")
        return
        
    all_trades = []
    
    logger.info("Evaluating Hikkake pattern across universe...")
    for sym, df in bulk_data.items():
        if len(df) < 50:
            continue
            
        evaluated_df = evaluate_hikkake(df)
        sym_trades = simulate_trades(evaluated_df, sym)
        all_trades.extend(sym_trades)
        
    logger.info(f"Generated {len(all_trades)} total trade signals over the historical period.")
    
    if not all_trades:
        logger.info("No trades found. Exiting.")
        return
        
    trades_df = pd.DataFrame(all_trades)
    
    # Export to CSV
    trades_df.to_csv(CSV_LOG_PATH, index=False)
    logger.info(f"Exported detailed trial logs to: {CSV_LOG_PATH}")
    
    # --- Metrics Computation ---
    print("\n" + "="*80)
    print("HIKKAKE BACKTEST METRICS".center(80))
    print("="*80)
    
    for cond in ["Bullish Fakeout", "Bearish Fakeout"]:
        sub_df = trades_df[trades_df['Condition'] == cond]
        if sub_df.empty:
            continue
            
        total = len(sub_df)
        win_rate_5d = len(sub_df[sub_df['PnL_5d_%'] > 0]) / total * 100
        win_rate_10d = len(sub_df[sub_df['PnL_10d_%'] > 0]) / total * 100
        avg_pnl_5d = sub_df['PnL_5d_%'].mean()
        avg_pnl_10d = sub_df['PnL_10d_%'].mean()
        avg_mfe = sub_df['Max_Profit_10d_%'].mean()
        avg_mae = sub_df['Max_Drawdown_10d_%'].mean()
        
        print(f"\nCondition: {cond}")
        print("-" * 40)
        print(f"Total Occurrences  : {total}")
        print(f"Win Rate (5 Days)  : {win_rate_5d:.2f}%")
        print(f"Avg PnL (5 Days)   : {avg_pnl_5d:.2f}%")
        print(f"Win Rate (10 Days) : {win_rate_10d:.2f}%")
        print(f"Avg PnL (10 Days)  : {avg_pnl_10d:.2f}%")
        print(f"Avg Max Profit     : +{avg_mfe:.2f}% (over 10d)")
        print(f"Avg Max Drawdown   : {avg_mae:.2f}% (over 10d)")
        
    # --- Overall Metrics ---
    total_all = len(trades_df)
    win_rate_all_5d = len(trades_df[trades_df['PnL_5d_%'] > 0]) / total_all * 100
    win_rate_all_10d = len(trades_df[trades_df['PnL_10d_%'] > 0]) / total_all * 100
    avg_pnl_all_5d = trades_df['PnL_5d_%'].mean()
    avg_pnl_all_10d = trades_df['PnL_10d_%'].mean()
    total_cumulative_pnl = trades_df['PnL_10d_%'].sum()
    
    print("\n" + "="*80)
    print("OVERALL COMBINED METRICS".center(80))
    print("="*80)
    print(f"Total Occurrences   : {total_all}")
    print(f"Overall Win Rate 5d : {win_rate_all_5d:.2f}%")
    print(f"Overall Win Rate 10d: {win_rate_all_10d:.2f}%")
    print(f"Overall Avg PnL 10d : {avg_pnl_all_10d:.2f}% per trade")
    print(f"Cumulative PnL      : {total_cumulative_pnl:.2f}% (sum of all 10d PnLs)")
    print("="*80 + "\n")
    
if __name__ == "__main__":
    main()
