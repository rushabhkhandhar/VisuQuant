"""
BTST (Buy Today, Sell Tomorrow) Gap Hunter Screener
===================================================
Run at 3:15 PM to capture overnight gap-ups by buying stocks that show 
intense accumulation in the final hour of trading, closing near HOD.

Usage:
    cd Quant_backend
    python3 src/screener/pipeline/run_btst_hunter.py
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
HOD_PROXIMITY_PCT = 1.0         # Must be within 1% of High of Day
MIN_LIQUIDITY_THRESHOLD = 5e7   # ₹5 crore daily avg volume
TOP_N_CANDIDATES = 5

# Output paths
FRONT_TEST_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))),
    "front_testing"
)
os.makedirs(FRONT_TEST_DIR, exist_ok=True)


# ============================================================================
# INDICATORS & FILTERS
# ============================================================================

def filter_btst_hunter(sym, daily_df, m15_df):
    """
    F1: Trading within 1% of High of the Day (HOD).
    F2: Volume in the 2:15-3:15 PM window > average.
    F3: Closing above the 20-day high (daily breakout).
    """
    if len(daily_df) < 20 or m15_df is None or m15_df.empty:
        return False, {}
        
    # Liquidity check (daily_df is historical EOD data, no live candle to strip)
    hist_daily = daily_df
    avg_traded_value = (hist_daily['Close'].tail(20) * hist_daily['Volume'].tail(20)).mean()
    if avg_traded_value < MIN_LIQUIDITY_THRESHOLD:
        return False, {}
        
    # Get today's intraday data
    m15_df['Date'] = m15_df.index.date
    today_data = m15_df[m15_df['Date'] == date.today()]
    
    if today_data.empty:
        # Fallback for after-hours testing
        last_date = m15_df['Date'].iloc[-1]
        today_data = m15_df[m15_df['Date'] == last_date]
        if today_data.empty:
            return False, {}
            
    # 1. Proximity to HOD
    hod = today_data['High'].max()
    current_price = today_data['Close'].iloc[-1]
    
    dist_to_hod_pct = ((hod - current_price) / hod) * 100
    if dist_to_hod_pct > HOD_PROXIMITY_PCT:
        return False, {}
        
    # 2. Daily Breakout (closing > 20-day high)
    high_20d = hist_daily['High'].tail(20).max()
    if current_price <= high_20d:
        return False, {}
        
    # 3. Final Hour Volume Check
    if len(today_data) >= 4:
        # Last 4 candles = last hour (2:15 to 3:15)
        final_hour_vol = today_data['Volume'].tail(4).sum()
        
        # Compare to average volume of previous hours today (if available)
        earlier_vol = today_data['Volume'].iloc[:-4].sum()
        avg_hourly_earlier = earlier_vol / max(1, (len(today_data) - 4) / 4)
        
        if final_hour_vol <= avg_hourly_earlier * 1.5: # Want 50% more volume than average
            return False, {}
    else:
        return False, {} # Not enough data today
        
    return True, {
        "Symbol": sym,
        "Current_Price": round(current_price, 2),
        "Dist_to_HOD_Pct": round(dist_to_hod_pct, 2),
        "Breakout_Level": round(high_20d, 2),
        "Vol_Surge": round(final_hour_vol / avg_hourly_earlier, 2) if avg_hourly_earlier > 0 else 0
    }

# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    logger.info("Starting BTST Gap Hunter Screener...")
    
    symbols = load_nifty500_symbols()
    logger.info(f"Universe: {len(symbols)} stocks")
    
    fetcher = get_tv_fetcher()
    
    # Fetch 15-minute data
    logger.info("Fetching 15-minute data...")
    m15_data = fetcher.fetch_bulk_intraday(symbols, interval=Interval.in_15_minute, n_bars=100)
    
    # Fetch daily data
    logger.info("Fetching historical Daily data (bypassing TradingView)...")
    daily_data = fetch_bulk_history(symbols, end_date=date.today(), lookback_days=30)
    
    candidates = []
    
    for sym in symbols:
        if sym not in daily_data or sym not in m15_data:
            continue
            
        passed, details = filter_btst_hunter(sym, daily_data[sym], m15_data[sym])
        if passed:
            candidates.append(details)
            
    # Rank by how close they are to HOD
    candidates.sort(key=lambda x: x['Dist_to_HOD_Pct'])
    top_candidates = candidates[:TOP_N_CANDIDATES]
    
    print("\n" + "*" * 80)
    print("BTST GAP HUNTER SCREENER (3:15 PM)".center(80))
    print("*" * 80)
    
    if not top_candidates:
        print("  No candidates passed the BTST criteria today.")
    else:
        print(f"  {'#':<3} {'SYMBOL':<12} {'PRICE':<8} {'DIST HOD%':<10} {'20D HIGH':<10} {'VOL SURGE'}")
        print("  " + "-" * 78)
        for i, c in enumerate(top_candidates, 1):
            print(f"  {i:<3} {c['Symbol']:<12} {c['Current_Price']:<8} {c['Dist_to_HOD_Pct']:<10} {c['Breakout_Level']:<10} {c['Vol_Surge']}x")
            
    print("\n  " + "-" * 78)
    print("  The Trade: Buy at 3:25 PM, Sell at 9:15 AM tomorrow.")
    print("=" * 80 + "\n")
    
    if top_candidates:
        csv_path = os.path.join(FRONT_TEST_DIR, f"btst_candidates_{date.today()}.csv")
        df_out = pd.DataFrame(top_candidates)
        df_out.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(top_candidates)} candidates to {csv_path}")

if __name__ == "__main__":
    main()
