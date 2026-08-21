"""
Intraday Opening Range Breakout (ORB) Screener
===============================================
Run at 10:15 AM IST to scan NIFTY 500 for stocks breaking out of their
9:15-10:15 AM opening range with institutional volume.

Usage:
    cd Quant_backend
    python3 src/screener/pipeline/run_intraday_orb.py
"""

import os
import sys
import csv
import logging
import pandas as pd
import numpy as np
from datetime import datetime, date, time as dtime

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

import talib
from tvDatafeed import Interval
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.data.live_tv_fetcher import get_tv_fetcher

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ============================================================================
# CONFIGURABLE PARAMETERS — Tune these, never hardcode values in the logic
# ============================================================================

SMA_SHORT = 20
SMA_LONG = 50
RSI_PERIOD = 14
ATR_PERIOD = 14
RSI_MIN = 55
RSI_MAX = 70
VOLUME_SURGE_MULTIPLIER = 2.0
MAX_RANGE_PCT_OF_ATR = 0.40
MIN_LIQUIDITY_THRESHOLD = 50_000_000  # ₹5 crore/day
TOP_N_CANDIDATES = 5
STOP_LOSS_METHOD = "candle_low"       # "candle_low" or "atr_multiple"
ATR_SL_MULTIPLE = 1.0                 # Used only if STOP_LOSS_METHOD == "atr_multiple"
TARGET_R_MULTIPLE = 2.0               # 2R target
HOURLY_LOOKBACK_DAYS = 20             # Days of hourly history for volume baseline
NIFTY_SYMBOL = "NIFTY"                # TradingView symbol for NIFTY 50 index

# Scoring weights (must sum to 1.0)
W_VOLUME = 0.35
W_RSI = 0.15
W_COIL = 0.25
W_TIER = 0.25

# Output paths
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)
CSV_OUTPUT = os.path.join(OUTPUT_DIR, "intraday_orb_signals.csv")


# ============================================================================
# INDICATOR HELPERS — Using TA-Lib for consistency with the rest of the codebase
# ============================================================================

def compute_sma(series, period):
    """Simple Moving Average via TA-Lib."""
    return pd.Series(talib.SMA(series.values, timeperiod=period), index=series.index)

def compute_rsi(series, period=14):
    """RSI via TA-Lib (Wilder's smoothing)."""
    return pd.Series(talib.RSI(series.values, timeperiod=period), index=series.index)

def compute_atr(high, low, close, period=14):
    """Average True Range via TA-Lib."""
    return pd.Series(talib.ATR(high.values, low.values, close.values, timeperiod=period), index=high.index)


# ============================================================================
# CORE FILTER FUNCTIONS — Each returns (passed: bool, details: dict)
# ============================================================================

def filter_liquidity(daily_df):
    """F0: Average daily traded value must exceed the liquidity floor."""
    if len(daily_df) < 20:
        return False, {"reason": "Not enough daily data for liquidity check"}
    
    # Use the live daily candle
    hist = daily_df
    last_20 = hist.tail(20)
    
    # Approximate traded value = Close * Volume
    avg_traded_value = (last_20['Close'] * last_20['Volume']).mean()
    
    if avg_traded_value < MIN_LIQUIDITY_THRESHOLD:
        return False, {"reason": f"Liquidity ₹{avg_traded_value/1e7:.2f}Cr < threshold"}
    
    return True, {"avg_traded_value": avg_traded_value}


def filter_daily_trend(daily_df):
    """F1: Price structure + RSI band on the daily chart.
    
    LOOK-AHEAD SAFEGUARD: Uses only completed daily candles (excludes today).
    """
    # Include today's live daily candle
    hist = daily_df
    
    if len(hist) < SMA_LONG + 10:
        return False, {"reason": "Not enough daily history for SMA50"}
    
    close = hist['Close']
    latest_close = close.iloc[-1]
    
    sma_short = compute_sma(close, SMA_SHORT).iloc[-1]
    sma_long = compute_sma(close, SMA_LONG).iloc[-1]
    rsi = compute_rsi(close, RSI_PERIOD).iloc[-1]
    
    if pd.isna(sma_short) or pd.isna(sma_long) or pd.isna(rsi):
        return False, {"reason": "NaN in daily indicators"}
    
    # Check: Close > SMA20 > SMA50
    if not (latest_close > sma_short and sma_short > sma_long):
        return False, {"reason": f"Trend structure failed: Close={latest_close:.2f}, SMA20={sma_short:.2f}, SMA50={sma_long:.2f}"}
    
    # Check: RSI in [55, 70]
    if not (RSI_MIN <= rsi <= RSI_MAX):
        return False, {"reason": f"RSI {rsi:.1f} outside [{RSI_MIN}, {RSI_MAX}]"}
    
    return True, {"rsi": rsi, "sma_short": sma_short, "sma_long": sma_long}


def filter_market_regime(nifty_daily_df, nifty_hourly_df):
    """F2: NIFTY must be in an uptrend and green since today's open."""
    # Daily: NIFTY close > SMA20 (using live candle instead of completed)
    hist = nifty_daily_df
    if len(hist) < SMA_SHORT + 5:
        return False, {"reason": "Not enough NIFTY daily data"}
    
    nifty_close = hist['Close'].iloc[-1]
    nifty_sma20 = compute_sma(hist['Close'], SMA_SHORT).iloc[-1]
    
    logger.info(f"NIFTY Regime Check -> Live Price: {nifty_close:.2f} | SMA20: {nifty_sma20:.2f}")
    
    if pd.isna(nifty_sma20) or nifty_close <= nifty_sma20:
        return False, {"reason": f"NIFTY below SMA20: {nifty_close:.2f} vs {nifty_sma20:.2f}"}
    
    # Intraday: NIFTY change since today's open > 0
    if nifty_hourly_df is not None and not nifty_hourly_df.empty:
        # The most recent hourly candle is today's first hour (9:15-10:15)
        today_first_candle = nifty_hourly_df.iloc[-1]
        nifty_intraday_change = today_first_candle['Close'] - today_first_candle['Open']
        
        if nifty_intraday_change <= 0:
            return False, {"reason": f"NIFTY intraday red: change={nifty_intraday_change:.2f}"}
    
    return True, {"nifty_close": nifty_close, "nifty_sma20": nifty_sma20}


def extract_first_hour_candle(hourly_df):
    """Extract today's 9:15-10:15 candle from hourly data.
    
    TradingView hourly candles are timestamped at the candle OPEN time.
    The 9:15 AM candle represents 9:15-10:15 and is the most recent one
    when the script runs at 10:15 AM.
    
    Returns: (candle_dict, historical_first_hour_candles) or (None, None)
    """
    if hourly_df is None or hourly_df.empty:
        return None, None
    
    # The last row is today's 9:15-10:15 candle (the one that just closed)
    today_candle = hourly_df.iloc[-1]
    
    # For historical baseline: get the 9:15 AM candle from prior days
    # TradingView timestamps hourly candles at the candle open.
    # The 9:15 AM candle has hour=9 and minute=15 (IST)
    # We need to find candles that match this time across previous days.
    historical_first_hour = []
    
    for idx, row in hourly_df.iloc[:-1].iterrows():
        # TradingView index is datetime; check if it's a 9:15 candle
        if hasattr(idx, 'hour'):
            if idx.hour == 9 and idx.minute == 15:
                historical_first_hour.append(row)
        elif hasattr(idx, 'time'):
            t = idx.time()
            if t.hour == 9 and t.minute == 15:
                historical_first_hour.append(row)
    
    candle = {
        "open": today_candle['Open'],
        "high": today_candle['High'],
        "low": today_candle['Low'],
        "close": today_candle['Close'],
        "volume": today_candle['Volume'],
        "range": today_candle['High'] - today_candle['Low']
    }
    
    return candle, historical_first_hour


def filter_volume_surge(today_candle, historical_first_hour):
    """F3: Today's 9:15-10:15 volume vs historical average of the same candle.
    
    LOOK-AHEAD SAFEGUARD: Only compares to historical 9:15-10:15 candles,
    never to today's later candles.
    """
    if not historical_first_hour or len(historical_first_hour) < 5:
        return False, {"reason": f"Only {len(historical_first_hour) if historical_first_hour else 0} historical first-hour candles (need >= 5)"}
    
    # Use only the last HOURLY_LOOKBACK_DAYS entries
    lookback = historical_first_hour[-HOURLY_LOOKBACK_DAYS:]
    
    hist_volumes = [c['Volume'] for c in lookback]
    avg_hist_volume = np.mean(hist_volumes)
    
    if avg_hist_volume <= 0:
        return False, {"reason": "Historical average volume is zero"}
    
    volume_ratio = today_candle['volume'] / avg_hist_volume
    
    if volume_ratio < VOLUME_SURGE_MULTIPLIER:
        return False, {"reason": f"Volume ratio {volume_ratio:.2f}x < {VOLUME_SURGE_MULTIPLIER}x"}
    
    return True, {"volume_ratio": round(volume_ratio, 2)}


def filter_coiled_spring(today_candle, daily_df):
    """F4: First hour range must be less than MAX_RANGE_PCT_OF_ATR of Daily ATR14.
    
    LOOK-AHEAD SAFEGUARD: ATR computed from completed daily candles only.
    """
    # Include today's live daily candle
    hist = daily_df
    
    if len(hist) < ATR_PERIOD + 5:
        return False, {"reason": "Not enough daily data for ATR"}
    
    atr = compute_atr(hist['High'], hist['Low'], hist['Close'], ATR_PERIOD).iloc[-1]
    
    if pd.isna(atr) or atr <= 0:
        return False, {"reason": "ATR is NaN or zero"}
    
    candle_range = today_candle['range']
    range_pct = candle_range / atr
    
    if range_pct >= MAX_RANGE_PCT_OF_ATR:
        return False, {"reason": f"Range {range_pct:.2f} >= {MAX_RANGE_PCT_OF_ATR} of ATR"}
    
    return True, {"candle_range_pct_atr": round(range_pct, 4), "daily_atr": round(atr, 2)}


def filter_clean_air(today_candle, daily_df):
    """F5: 10:15 high must clear prior-day high AND approach/exceed 20-day high.
    
    LOOK-AHEAD SAFEGUARD: 20-day high and 52-week high computed from
    completed daily candles only (excludes today).
    """
    # Include today's live daily candle
    hist = daily_df
    
    if len(hist) < 20:
        return False, {"reason": "Not enough daily data for resistance check"}
    
    orb_high = today_candle['high']
    prior_day_high = hist['High'].iloc[-1]
    high_20d = hist['High'].tail(20).max()
    
    # Check 1: Must be above yesterday's high
    if orb_high <= prior_day_high:
        return False, {"reason": f"ORB high {orb_high:.2f} <= prior day high {prior_day_high:.2f}"}
    
    # Check 2: Must be near or above 20-day high (within 2%)
    if orb_high < high_20d * 0.98:
        return False, {"reason": f"ORB high {orb_high:.2f} < 98% of 20d high {high_20d:.2f}"}
    
    # Determine tier
    high_52w = hist['High'].tail(252).max() if len(hist) >= 252 else hist['High'].max()
    
    if orb_high > high_52w:
        tier = 1
        resistance_cleared = "52w_high"
    elif orb_high > high_20d:
        tier = 2
        resistance_cleared = "20d_high"
    else:
        tier = 3
        resistance_cleared = "prior_day"
    
    return True, {
        "tier": tier,
        "resistance_cleared": resistance_cleared,
        "prior_day_high": round(prior_day_high, 2),
        "high_20d": round(high_20d, 2),
        "high_52w": round(high_52w, 2)
    }


# ============================================================================
# SCORING
# ============================================================================

def compute_score(volume_ratio, rsi, candle_range_pct_atr, tier):
    """Composite score to rank candidates. Higher is better."""
    # Volume component: cap at 5x to prevent outliers from dominating
    vol_score = min(volume_ratio, 5.0) / 5.0
    
    # RSI proximity to 62.5 (center of [55, 70] band)
    rsi_ideal = (RSI_MIN + RSI_MAX) / 2.0
    rsi_score = 1.0 - abs(rsi - rsi_ideal) / (rsi_ideal - RSI_MIN)
    rsi_score = max(0.0, min(1.0, rsi_score))
    
    # Coil tightness: tighter = better
    coil_score = 1.0 - (candle_range_pct_atr / MAX_RANGE_PCT_OF_ATR)
    coil_score = max(0.0, min(1.0, coil_score))
    
    # Tier bonus
    tier_bonus_map = {1: 1.0, 2: 0.5, 3: 0.0}
    tier_score = tier_bonus_map.get(tier, 0.0)
    
    score = (vol_score * W_VOLUME) + (rsi_score * W_RSI) + (coil_score * W_COIL) + (tier_score * W_TIER)
    return round(score, 4)


# ============================================================================
# EXIT LOGIC
# ============================================================================

def compute_exits(today_candle, daily_df):
    """Compute stop loss, target, and time-exit for a candidate."""
    # Include today's live daily candle
    hist = daily_df
    atr = compute_atr(hist['High'], hist['Low'], hist['Close'], ATR_PERIOD).iloc[-1]
    
    entry_price = today_candle['high']  # Stop-limit buy above the high
    
    if STOP_LOSS_METHOD == "candle_low":
        stop_loss = today_candle['low']
    else:  # atr_multiple
        stop_loss = entry_price - (ATR_SL_MULTIPLE * atr)
    
    risk = entry_price - stop_loss
    target = entry_price + (risk * TARGET_R_MULTIPLE)
    
    return {
        "entry_trigger_price": round(entry_price, 2),
        "stop_loss": round(stop_loss, 2),
        "target_2r": round(target, 2),
        "risk_per_share": round(risk, 2)
    }


# ============================================================================
# CSV OUTPUT
# ============================================================================

CSV_COLUMNS = [
    "Date", "Time", "Symbol", "Score", "Tier", "Entry_Trigger_Price",
    "Stop_Loss", "Target_2R", "Risk_Per_Share", "Volume_Ratio",
    "Candle_Range_Pct_ATR", "RSI_Daily", "Resistance_Cleared", "Outcome"
]

def save_to_csv(candidates):
    """Append candidates to CSV. Creates file with header if it doesn't exist."""
    file_exists = os.path.exists(CSV_OUTPUT)
    
    with open(CSV_OUTPUT, 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        if not file_exists:
            writer.writeheader()
        
        for c in candidates:
            writer.writerow(c)
    
    logger.info(f"Saved {len(candidates)} candidates to {CSV_OUTPUT}")


# ============================================================================
# TERMINAL OUTPUT
# ============================================================================

def print_results(candidates, regime_info):
    print("\n" + "*" * 80)
    print("INTRADAY ORB SCREENER — 10:15 AM SCAN".center(80))
    print("*" * 80)
    
    scan_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"\n  Scan Time     : {scan_time}")
    print(f"  Market Regime : {'✅ Bullish' if regime_info.get('passed') else '❌ Bearish/Flat'}")
    print(f"  Filters       : Liquidity > ₹{MIN_LIQUIDITY_THRESHOLD/1e7:.0f}Cr | RSI [{RSI_MIN}-{RSI_MAX}] | Vol Surge > {VOLUME_SURGE_MULTIPLIER}x | Coil < {MAX_RANGE_PCT_OF_ATR} ATR")
    print(f"  Candidates    : {len(candidates)} / {TOP_N_CANDIDATES} max\n")
    
    if not candidates:
        print("  No candidates passed all filters today.")
        print("=" * 80 + "\n")
        return
    
    print(f"  {'#':<3} {'SYMBOL':<12} {'SCORE':<7} {'TIER':<5} {'ENTRY':<10} {'SL':<10} {'TGT(2R)':<10} {'VOL_X':<7} {'COIL':<6} {'RSI':<5} {'RESISTANCE'}")
    print("  " + "-" * 78)
    
    for i, c in enumerate(candidates, 1):
        tier_label = {1: "T1★", 2: "T2", 3: "T3"}.get(c.get("_tier", 3), "T3")
        print(f"  {i:<3} {c['Symbol']:<12} {c['Score']:<7} {tier_label:<5} {c['Entry_Trigger_Price']:<10} {c['Stop_Loss']:<10} {c['Target_2R']:<10} {c['Volume_Ratio']:<7} {c['Candle_Range_Pct_ATR']:<6} {c['RSI_Daily']:<5} {c['Resistance_Cleared']}")
    
    print("\n  " + "-" * 78)
    print(f"  Stop Loss Method: {STOP_LOSS_METHOD.upper()} | Target: {TARGET_R_MULTIPLE}R | Time Exit: 3:15 PM")
    print(f"  Place STOP-LIMIT BUY orders at Entry Trigger Price on your broker.")
    print("=" * 80 + "\n")


# ============================================================================
# MAIN PIPELINE
# ============================================================================

def main():
    logger.info("=" * 60)
    logger.info("Starting Intraday ORB Screener...")
    logger.info("=" * 60)
    
    # 1. Load universe
    logger.info("Loading NIFTY 500 universe...")
    symbols = load_nifty500_symbols()
    logger.info(f"Universe: {len(symbols)} stocks")
    
    # 2. Initialize fetcher
    fetcher = get_tv_fetcher()
    
    # 3. Fetch NIFTY index data first (for regime filter)
    logger.info("Fetching NIFTY 50 index data (daily + hourly)...")
    nifty_daily = fetcher.fetch_symbol(NIFTY_SYMBOL, n_bars=60)
    nifty_hourly = fetcher.fetch_symbol_intraday(NIFTY_SYMBOL, interval=Interval.in_1_hour, n_bars=200)
    
    # 3a. Check market regime FIRST — if bearish, skip the entire scan
    if nifty_daily is None or nifty_daily.empty:
        logger.error("Failed to fetch NIFTY daily data. Cannot determine regime. Aborting.")
        return
    
    regime_passed, regime_info = filter_market_regime(nifty_daily, nifty_hourly)
    regime_info['passed'] = regime_passed
    
    # if not regime_passed:
    #     logger.warning(f"Market regime filter FAILED: {regime_info.get('reason', 'Unknown')}")
    #     logger.warning("Skipping scan — do not trade ORB against a falling market.")
    #     print_results([], regime_info)
    #     return
    
    logger.info("Market regime: ✅ Bullish — proceeding with scan.")
    
    # 4. Fetch daily data for all symbols instantly using nse_fetcher
    logger.info("Fetching daily historical data for universe (instant cache)...")
    daily_data = fetch_bulk_history(symbols, end_date=date.today(), lookback_days=300)
    
    # 5. Fetch hourly data for all symbols
    logger.info("Fetching live hourly data for universe (Sequential TV Mode)...")
    hourly_data = fetcher.fetch_bulk_intraday(symbols, interval=Interval.in_1_hour, n_bars=200)
    
    # 6. Run filter pipeline
    logger.info("Running filter pipeline...")
    all_candidates = []
    passed_vol_surge = []
    passed_coil = []
    filter_stats = {"total": len(symbols), "f0": 0, "f1": 0, "f3": 0, "f4": 0, "f5": 0}
    
    for sym in symbols:
        if sym not in daily_data or sym not in hourly_data:
            continue
        
        daily_df = daily_data[sym]
        hourly_df = hourly_data[sym]
        
        # F0: Liquidity
        passed, details = filter_liquidity(daily_df)
        if not passed:
            continue
        filter_stats["f0"] += 1
        
        # F1: Daily Trend
        passed, trend_details = filter_daily_trend(daily_df)
        if not passed:
            continue
        filter_stats["f1"] += 1
        
        # Extract first hour candle
        today_candle, hist_first_hour = extract_first_hour_candle(hourly_df)
        if today_candle is None:
            continue
        
        # F3: Volume Surge
        passed, vol_details = filter_volume_surge(today_candle, hist_first_hour)
        if not passed:
            continue
        filter_stats["f3"] += 1
        passed_vol_surge.append(sym)
        
        # F4: Coiled Spring
        passed, coil_details = filter_coiled_spring(today_candle, daily_df)
        if not passed:
            continue
        filter_stats["f4"] += 1
        passed_coil.append(sym)
        
        # F5: Clean Air
        passed, air_details = filter_clean_air(today_candle, daily_df)
        if not passed:
            continue
        filter_stats["f5"] += 1
        
        # Compute exits
        exits = compute_exits(today_candle, daily_df)
        
        # Compute score
        score = compute_score(
            vol_details['volume_ratio'],
            trend_details['rsi'],
            coil_details['candle_range_pct_atr'],
            air_details['tier']
        )
        
        candidate = {
            "Date": date.today().strftime("%Y-%m-%d"),
            "Time": datetime.now().strftime("%H:%M"),
            "Symbol": sym,
            "Score": score,
            "Tier": air_details['tier'],
            "Entry_Trigger_Price": exits['entry_trigger_price'],
            "Stop_Loss": exits['stop_loss'],
            "Target_2R": exits['target_2r'],
            "Risk_Per_Share": exits['risk_per_share'],
            "Volume_Ratio": vol_details['volume_ratio'],
            "Candle_Range_Pct_ATR": coil_details['candle_range_pct_atr'],
            "RSI_Daily": round(trend_details['rsi'], 1),
            "Resistance_Cleared": air_details['resistance_cleared'],
            "Outcome": "",  # To be filled manually at EOD
            "_tier": air_details['tier']  # Internal use for display
        }
        
        all_candidates.append(candidate)
    
    # Log filter funnel
    logger.info(f"Filter funnel: Total={filter_stats['total']} → "
                f"Liquidity={filter_stats['f0']} → Trend={filter_stats['f1']} → "
                f"VolSurge={filter_stats['f3']} → Coil={filter_stats['f4']} → "
                f"CleanAir={filter_stats['f5']}")
    
    if passed_vol_surge:
        logger.info(f"🔍 MANUAL TRACKING: Passed Volume Surge ({len(passed_vol_surge)} stocks): {', '.join(passed_vol_surge)}")
    if passed_coil:
        logger.info(f"🔍 MANUAL TRACKING: Passed Coiled Spring ({len(passed_coil)} stocks): {', '.join(passed_coil)}")
    
    # 7. Rank and select top N
    all_candidates.sort(key=lambda x: x['Score'], reverse=True)
    top_candidates = all_candidates[:TOP_N_CANDIDATES]
    
    # 8. Output
    print_results(top_candidates, regime_info)
    
    if top_candidates:
        # Remove internal keys before saving to CSV
        csv_candidates = [{k: v for k, v in c.items() if not k.startswith('_')} for c in top_candidates]
        save_to_csv(csv_candidates)
    else:
        logger.info("No candidates to save.")
    
    logger.info("ORB scan complete.")


if __name__ == "__main__":
    main()
