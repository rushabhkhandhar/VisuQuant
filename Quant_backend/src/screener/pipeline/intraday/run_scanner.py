import os
import sys
import logging
from datetime import datetime, date
import pandas as pd

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from tvDatafeed import Interval
from src.data.nse_fetcher import fetch_bulk_history, load_nifty50_symbols, load_nifty100_symbols
from src.data.live_tv_fetcher import get_tv_fetcher

from src.screener.pipeline.intraday.config import STRATEGY_CONFIG, SECTOR_MAPPING
from src.screener.pipeline.intraday.features import (
    calculate_gap, calculate_or, calculate_vwap, 
    calculate_time_of_day_rvol, calculate_relative_strength
)
from src.screener.pipeline.intraday.scoring import compute_signal_score

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def load_universe(universe_name):
    if universe_name == "NIFTY_50":
        return load_nifty50_symbols()
    elif universe_name == "NIFTY_100":
        return load_nifty100_symbols()
    else:
        # Fallback to 100 for live scanner performance by default
        return load_nifty100_symbols()

def scan_market(current_time_str="10:00"):
    """
    Run the intraday scanner to find top ORB + RVOL setups up to a certain time of day.
    """
    fetcher = get_tv_fetcher()
    symbols = load_universe(STRATEGY_CONFIG['universe'])
    logger.info(f"Loaded {len(symbols)} symbols from {STRATEGY_CONFIG['universe']}")
    
    # 1. Fetch Daily Data for Gap calculation and ATR
    logger.info("Fetching EOD daily data...")
    daily_data = fetch_bulk_history(symbols + ["NIFTY"], end_date=date.today(), lookback_days=20)
    
    # 2. Fetch 5m Intraday Data
    logger.info(f"Fetching 5m intraday data from TradingView...")
    # Get enough history to cover lookback_days of time-of-day volume (75 candles per day * 25 days = ~2000 candles)
    n_bars = 75 * (STRATEGY_CONFIG['rvol_lookback_days'] + 5) 
    
    intraday_data = fetcher.fetch_bulk_intraday(symbols + ["NIFTY"], interval=Interval.in_5_minute, n_bars=n_bars)
    
    # Precompute NIFTY features
    nifty_d = daily_data.get("NIFTY")
    nifty_i = intraday_data.get("NIFTY")
    if nifty_i is None or nifty_i.empty:
        logger.error("Failed to fetch NIFTY data.")
        return
        
    nifty_vwap_df = calculate_vwap(nifty_i)
    
    # Filter for up to current_time_str
    nifty_up_to_t = nifty_i.between_time('09:15', current_time_str)
    
    results = []
    
    for sym in symbols:
        d_df = daily_data.get(sym)
        i_df = intraday_data.get(sym)
        
        if d_df is None or i_df is None or i_df.empty:
            continue
            
        # Ensure we have data up to current time
        i_df_t = i_df.between_time('09:15', current_time_str)
        if i_df_t.empty:
            continue
            
        current_price = i_df_t['Close'].iloc[-1]
        
        # Calculate Features
        gap_pct, prev_close = calculate_gap(d_df[d_df.index.date < date.today()], current_price)
        
        or_data = calculate_or(
            i_df[i_df.index.date == date.today()], 
            STRATEGY_CONFIG['or_start_time'], 
            STRATEGY_CONFIG['or_end_time']
        )
        if not or_data: continue
        
        rvol, today_vol, avg_vol = calculate_time_of_day_rvol(i_df, current_time_str, STRATEGY_CONFIG['rvol_lookback_days'])
        
        vwap_df = calculate_vwap(i_df)
        vwap = vwap_df['VWAP'].iloc[-1]
        vwap_slope = vwap_df['VWAP_Slope'].iloc[-1]
        
        rs = calculate_relative_strength(i_df_t[i_df_t.index.date == date.today()], nifty_up_to_t[nifty_up_to_t.index.date == date.today()])
        
        # Breakout Vol Ratio
        bo_vol_ratio = 0
        if current_price > or_data['orh'] or current_price < or_data['orl']:
            # Volume of the latest candle compared to average
            bo_vol_ratio = i_df_t['Volume'].iloc[-1] / (avg_vol / len(i_df_t)) if avg_vol > 0 else 0
            
        # R:R Calculation (assuming Stop at OR Mid, Target at 2x distance)
        # This is a generic R:R just for scoring
        rr = 0
        sl_dist = abs(current_price - ((or_data['orh'] + or_data['orl'])/2))
        if sl_dist > 0:
            target_dist = sl_dist * STRATEGY_CONFIG['target_r_multiple']
            rr = target_dist / sl_dist
            
        features = {
            "current_price": current_price,
            "gap_pct": gap_pct,
            "orh": or_data['orh'],
            "orl": or_data['orl'],
            "or_width_pct": or_data['or_width_pct'],
            "rvol": rvol,
            "vwap": vwap,
            "vwap_slope": vwap_slope,
            "breakout_vol_ratio": bo_vol_ratio,
            "relative_strength": rs,
            "nifty_price": nifty_up_to_t['Close'].iloc[-1],
            "nifty_vwap": nifty_vwap_df['VWAP'].iloc[-1],
            "rr": rr
        }
        
        # Score Long
        long_score, long_reasons = compute_signal_score(STRATEGY_CONFIG, features, "LONG")
        # Score Short
        short_score, short_reasons = compute_signal_score(STRATEGY_CONFIG, features, "SHORT")
        
        if long_score > short_score:
            results.append({
                "Symbol": sym,
                "Direction": "LONG",
                "Score": long_score,
                "Gap": gap_pct,
                "RVOL": rvol,
                "VWAP": "Above" if current_price > vwap else "Below",
                "ORB": "ORH Break" if current_price > or_data['orh'] else "In Range",
                "RS": rs,
                "Reasons": " | ".join(long_reasons)
            })
        else:
            results.append({
                "Symbol": sym,
                "Direction": "SHORT",
                "Score": short_score,
                "Gap": gap_pct,
                "RVOL": rvol,
                "VWAP": "Above" if current_price > vwap else "Below",
                "ORB": "ORL Break" if current_price < or_data['orl'] else "In Range",
                "RS": rs,
                "Reasons": " | ".join(short_reasons)
            })
            
    df_results = pd.DataFrame(results)
    if not df_results.empty:
        df_results = df_results.sort_values(by="Score", ascending=False)
        print("\n--- TOP INTRADAY CANDIDATES ---")
        print(df_results.head(10).to_string(index=False))
        
if __name__ == "__main__":
    scan_market()
