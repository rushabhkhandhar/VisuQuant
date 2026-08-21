"""
Mid-Session VWAP Pullback Screener
===================================
Run at 12:30 PM or 1:30 PM to find stocks that had a strong morning push,
and are now resting near their Intraday VWAP on low volume.

Usage:
    cd Quant_backend
    python3 src/screener/pipeline/run_vwap_pullback.py
"""

import os
import sys
import logging
import pandas as pd
from datetime import datetime, date

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from tvDatafeed import Interval
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.data.live_tv_fetcher import get_tv_fetcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURABLE PARAMETERS
# ============================================================================
MIN_UP_PCT = 2.0                # Must be up at least 2% on the day
VWAP_PROXIMITY_PCT = 0.5        # Must be within 0.5% of VWAP (above it)
MIN_LIQUIDITY_THRESHOLD = 5e7   # ₹5 crore daily avg volume
TOP_N_CANDIDATES = 5

# Output paths
FRONT_TEST_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "outputs")
os.makedirs(FRONT_TEST_DIR, exist_ok=True)


# ============================================================================
# INDICATORS & FILTERS
# ============================================================================

def calculate_vwap(df):
    """Calculate daily VWAP for an intraday dataframe."""
    df = df.copy()
    df['Date'] = df.index.date
    df['Typical_Price'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['PV'] = df['Typical_Price'] * df['Volume']
    
    df['Cum_Vol'] = df.groupby('Date')['Volume'].cumsum()
    df['Cum_PV'] = df.groupby('Date')['PV'].cumsum()
    df['VWAP'] = df['Cum_PV'] / df['Cum_Vol']
    
    return df

def filter_vwap_pullback(sym, daily_df, m15_df):
    """
    F1: Up > 2% for the day.
    F2: Current price within 0.5% of VWAP and > VWAP.
    F3: Pullback volume < Morning surge volume.
    """
    if len(daily_df) < 20 or m15_df is None or m15_df.empty:
        return False, {}
        
    # Liquidity check (daily_df is historical EOD data, no live candle to strip)
    hist_daily = daily_df
    avg_traded_value = (hist_daily['Close'].tail(20) * hist_daily['Volume'].tail(20)).mean()
    if avg_traded_value < MIN_LIQUIDITY_THRESHOLD:
        return False, {}
        
    # 1. Up > 2% for the day
    prev_close = hist_daily['Close'].iloc[-1]
    current_price = m15_df['Close'].iloc[-1]
    day_pct_change = ((current_price - prev_close) / prev_close) * 100
    
    if day_pct_change < MIN_UP_PCT:
        return False, {}
        
    # 2. VWAP Calculation
    m15_df = calculate_vwap(m15_df)
    today_data = m15_df[m15_df['Date'] == date.today()]
    
    if today_data.empty or len(today_data) < 3: # Need at least a few 15m candles
        # Fallback to the last day in the dataset if today's data is empty (for after-hours testing)
        last_date = m15_df['Date'].iloc[-1]
        today_data = m15_df[m15_df['Date'] == last_date]
        if today_data.empty or len(today_data) < 3:
            return False, {}
            
    current_vwap = today_data['VWAP'].iloc[-1]
    current_close = today_data['Close'].iloc[-1]
    
    # Must be at or slightly above VWAP
    if current_close < current_vwap:
        return False, {}
        
    vwap_distance_pct = ((current_close - current_vwap) / current_vwap) * 100
    if vwap_distance_pct > VWAP_PROXIMITY_PCT:
        return False, {}
        
    # 3. Volume Check: Morning surge vs recent pullback
    morning_candles = today_data.iloc[:4] # First hour (4 x 15m candles)
    recent_candles = today_data.iloc[-3:] # Last 45 mins
    
    max_morning_vol = morning_candles['Volume'].max()
    avg_pullback_vol = recent_candles['Volume'].mean()
    
    if avg_pullback_vol >= max_morning_vol:
        return False, {} # Volume didn't dry up
        
    return True, {
        "Symbol": sym,
        "Current_Price": round(current_close, 2),
        "Day_Pct": round(day_pct_change, 2),
        "VWAP": round(current_vwap, 2),
        "Dist_to_VWAP_Pct": round(vwap_distance_pct, 2),
        "Morning_Max_Vol": max_morning_vol,
        "Pullback_Avg_Vol": round(avg_pullback_vol, 0)
    }

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    logger.info("Starting Mid-Session VWAP Pullback Screener...")
    
    symbols = load_nifty500_symbols()
    logger.info(f"Universe: {len(symbols)} stocks")
    
    fetcher = get_tv_fetcher()
    
    # Fetch 15-minute data
    logger.info("Fetching 15-minute data...")
    m15_data = fetcher.fetch_bulk_intraday(symbols, interval=Interval.in_15_minute, n_bars=100)
    
    # Fetch daily data for liquidity and prev close using nse_fetcher (instant, bypasses TV completely!)
    logger.info("Fetching historical Daily data (bypassing TradingView)...")
    daily_data = fetch_bulk_history(symbols, end_date=date.today(), lookback_days=30)
    
    candidates = []
    
    for sym in symbols:
        if sym not in daily_data or sym not in m15_data:
            continue
            
        passed, details = filter_vwap_pullback(sym, daily_data[sym], m15_data[sym])
        if passed:
            candidates.append(details)
            
    # Rank by how close they are to VWAP (closest is best)
    candidates.sort(key=lambda x: x['Dist_to_VWAP_Pct'])
    top_candidates = candidates[:TOP_N_CANDIDATES]
    
    print("\n" + "*" * 80)
    print("MID-SESSION VWAP PULLBACK SCREENER".center(80))
    print("*" * 80)
    
    if not top_candidates:
        print("  No candidates passed the VWAP criteria today.")
    else:
        print(f"  {'#':<3} {'SYMBOL':<12} {'PRICE':<8} {'DAY %':<7} {'VWAP':<8} {'DIST %':<8} {'VOL DRY-UP'}")
        print("  " + "-" * 78)
        for i, c in enumerate(top_candidates, 1):
            vol_ratio = f"{c['Pullback_Avg_Vol'] / c['Morning_Max_Vol']:.2f}x"
            print(f"  {i:<3} {c['Symbol']:<12} {c['Current_Price']:<8} {c['Day_Pct']:<7} {c['VWAP']:<8} {c['Dist_to_VWAP_Pct']:<8} {vol_ratio}")
            
    print("=" * 80 + "\n")
    
    if top_candidates:
        csv_path = os.path.join(FRONT_TEST_DIR, f"vwap_candidates_{date.today()}.csv")
        df_out = pd.DataFrame(top_candidates)
        df_out.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(top_candidates)} candidates to {csv_path}")

if __name__ == "__main__":
    main()
