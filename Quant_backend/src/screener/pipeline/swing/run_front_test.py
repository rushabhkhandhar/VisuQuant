import os
import sys
import json
import csv
import logging
from datetime import date, datetime, timedelta
import pandas as pd
import numpy as np
import uuid
import talib
import requests
from dotenv import load_dotenv
from sklearn.linear_model import LinearRegression

# Load environment variables for Telegram
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), ".env")
load_dotenv(env_path)

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

# from src.screener.pipeline.run_custom_screen import run_custom_screener
from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols, cleanup_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

FRONT_TEST_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing")
os.makedirs(FRONT_TEST_DIR, exist_ok=True)

STATE_FILE = os.path.join(FRONT_TEST_DIR, "active_trades.json")
METRICS_FILE = os.path.join(FRONT_TEST_DIR, "metrics.csv")

# Global dict to track benchmark relative strength
BENCHMARK_RETURNS = {"20d": 0.0, "60d": 0.0}

def trend_pullback_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
    
    # 0. NIFTY REGIME FILTER (Avoid longs in market correction)
    if nifty_hist is not None and len(nifty_hist) > 50:
        nifty_ema50 = nifty_hist['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        if nifty_hist['Close'].iloc[-1] < nifty_ema50:
             return {"passed": False, "reasons": ["Nifty below 50 EMA"]}
             
    # 1. LONG-TERM TREND
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    ema50_20d_ago = df['Close'].ewm(span=50, adjust=False).mean().iloc[-20]
    close = df['Close'].iloc[-1]
    
    if not (close > sma200 and ema50 > sma200):
        return {"passed": False, "reasons": ["Failed Long-Term Trend"]}
        
    if ema50 <= ema50_20d_ago:
        return {"passed": False, "reasons": ["50 EMA is not rising"]}
        
    # 2. MEDIUM-TERM TREND
    if not (ema20 > ema50):
        return {"passed": False, "reasons": ["Failed Medium-Term Trend"]}
        
    # 4. RSI CONDITION (Slightly relaxed for deeper pullbacks)
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or not (40 <= rsi <= 65):
        return {"passed": False, "reasons": ["RSI not between 40 and 65"]}
        
    # 9. VOLATILITY
    atr = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(atr) or (atr / close) > 0.05:
        return {"passed": False, "reasons": ["High Volatility (ATR > 5%)"]}
        
    # 8. AVOID CHASING
    if close > (ema20 * 1.05):
        return {"passed": False, "reasons": ["Extended > 5% above 20 EMA"]}
        
    # 3. CONTROLLED PULLBACK & 5. SUPPORT & 6. PRICE ACTION
    # We want a pullback near 20 EMA or 50 EMA, and a bullish stabilization.
    # Check if close is near 20 or 50 EMA (within 3%)
    dist_20 = abs(close - ema20) / ema20
    dist_50 = abs(close - ema50) / ema50
    
    if dist_20 > 0.03 and dist_50 > 0.03:
         return {"passed": False, "reasons": ["Not near 20 or 50 EMA Support"]}
         
    # Bullish stabilization: Today's close > Today's open (green candle) and Today's close > Yesterday's high
    if close <= df['Open'].iloc[-1] or close <= df['High'].iloc[-2]:
         return {"passed": False, "reasons": ["No bullish confirmation"]}
         
    # Volume confirmation on the bounce
    vol = df['Volume'].iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if vol < vol_sma20:
        return {"passed": False, "reasons": ["Bounce volume below average"]}

    # Alpha score for quality ranking (Fix 2: MeanRev alpha)
    rsi_score = max(0.0, (65 - rsi) / 25)  # deeper pullback = higher score
    ema_score = max(0.0, 1.0 - (min(dist_20, dist_50) / 0.03))  # closer to EMA = higher
    vol_score = min(2.0, vol / vol_sma20) / 2.0  # volume ratio capped at 2x
    alpha_score = (rsi_score * 0.4) + (ema_score * 0.3) + (vol_score * 0.3)

    return {"passed": True, "score": 1.0, "alpha_score": alpha_score, "trigger_type": "Trend Pullback"}

def momentum_breakout_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    if nifty_hist is not None and len(nifty_hist) >= 60 and len(df) >= 60:
        n_20 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-20]) - 1
        n_60 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-60]) - 1
        s_20 = (df['Close'].iloc[-1] / df['Close'].iloc[-20]) - 1
        s_60 = (df['Close'].iloc[-1] / df['Close'].iloc[-60]) - 1
        
        if s_20 <= n_20 or s_60 <= n_60:
            return {"passed": False, "reasons": ["Relative Strength vs NIFTY failed"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. LONG-TERM TREND & 2. MEDIUM-TERM TREND
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 > ema50):
        return {"passed": False, "reasons": ["Failed Trend Conditions"]}
        
    # VCP (Volatility Contraction Pattern) CHECK
    # Check that the 10-day range before the breakout is tight (< 10%)
    recent_10d_high = df['High'].iloc[-11:-1].max()
    recent_10d_low = df['Low'].iloc[-11:-1].min()
    if recent_10d_low > 0:
        if (recent_10d_high - recent_10d_low) / recent_10d_low > 0.10:
            return {"passed": False, "reasons": ["VCP Failed (Too Volatile Before Breakout)"]}
        
    # 3. RESISTANCE BREAKOUT
    # Calculate the maximum high of the previous 40 trading days (excluding today)
    recent_resistance = df['High'].iloc[-41:-1].max()
    if close <= recent_resistance:
        return {"passed": False, "reasons": ["No Resistance Breakout"]}
        
    # 8. PRICE EXTENSION
    # Do not chase if price is already > 5% above the breakout level
    if close > (recent_resistance * 1.05):
        return {"passed": False, "reasons": ["Excessively Extended Breakout"]}
        
    # 4. BREAKOUT STRENGTH
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    day_range = high - low
    if day_range == 0 or ((close - low) / day_range) < 0.6:
        return {"passed": False, "reasons": ["Weak Close (Not near Highs)"]}
        
    # 5. VOLUME CONFIRMATION
    vol = df['Volume'].iloc[-1]
    avg_vol_20 = df['Volume'].rolling(20).mean().iloc[-2] # using past average
    if pd.isna(avg_vol_20) or vol < (2.0 * avg_vol_20):
        return {"passed": False, "reasons": ["Volume < 2.0x Average"]}
        
    # 6. RSI
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or rsi < 60:
        return {"passed": False, "reasons": ["RSI not > 60"]}
        
    # 7. MACD
    macd, macdsignal, macdhist = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
    if pd.isna(macd.iloc[-1]) or macd.iloc[-1] < macdsignal.iloc[-1]:
        return {"passed": False, "reasons": ["MACD below Signal Line"]}
        
    # 9. VOLATILITY
    atr = talib.ATR(df['High'], df['Low'], df['Close'], timeperiod=14).iloc[-1]
    # if pd.isna(atr) or (atr / close) > 0.05:
    #     return {"passed": False, "reasons": ["High Volatility (ATR > 5%)"]}


    return {"passed": True, "score": 1.0, "trigger_type": "Momentum Breakout"}

def oversold_uptrend_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    open_p = df['Open'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    prev_high = df['High'].iloc[-2]
    
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    
    if pd.isna(sma200) or pd.isna(ema50):
        return {"passed": False, "reasons": ["MAs not calculated"]}
        
    # 1. Long term bullish
    if not (close > sma200 and ema50 > sma200):
        return {"passed": False, "reasons": ["Not long-term bullish"]}
        
    # 2. RSI Condition
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or not (30 <= rsi <= 45):
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} not in (30, 45)"]}
        
    # 3. Support Proximity (near 50 EMA)
    dist_50 = abs(close - ema50) / ema50
    if dist_50 > 0.06 and close < ema50:
        return {"passed": False, "reasons": ["Broken too far below 50 EMA"]}
        
    # 4. Volatility
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    if atr / close > 0.05:
        return {"passed": False, "reasons": ["ATR > 5%"]}
        
    # 5. Reversal Confirmation
    candle_range = high - low
    if candle_range == 0:
        return {"passed": False, "reasons": ["Zero candle range"]}
    
    close_strength = (close - low) / candle_range
    is_strong_close = close_strength > 0.6
    is_engulfing = close > prev_high
    is_hammer = (open_p - low) / candle_range > 0.6 and (close - low) / candle_range > 0.6
    
    if not (is_strong_close or is_engulfing or is_hammer):
        return {"passed": False, "reasons": ["No reversal confirmation"]}

    # Alpha score for quality ranking (Fix 2: MeanRev alpha)
    rsi_score = max(0.0, (45 - rsi) / 15)  # deeper oversold = higher score
    ema_score = max(0.0, 1.0 - (dist_50 / 0.06))  # closer to 50 EMA = higher
    reversal_score = 0.0
    if is_engulfing: reversal_score = 1.0
    elif is_hammer: reversal_score = 0.8
    elif is_strong_close: reversal_score = 0.6
    alpha_score = (rsi_score * 0.4) + (ema_score * 0.3) + (reversal_score * 0.3)

    return {"passed": True, "score": 1.0, "alpha_score": alpha_score, "trigger_type": "Oversold Uptrend"}

def volatility_compression_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. & 2. TRENDS
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 >= ema50):
        return {"passed": False, "reasons": ["Trend not aligned"]}
        
    # 3. CONSOLIDATION (Look at past 10 days excluding today)
    past_10_high = df['High'].iloc[-11:-1].max()
    past_10_low = df['Low'].iloc[-11:-1].min()
    consolidation_range = (past_10_high - past_10_low) / past_10_low
    
    if consolidation_range > 0.06: # Max 6% consolidation range
        return {"passed": False, "reasons": ["Consolidation too loose (>6%)"]}
        
    # 8. BREAKOUT & 5. RESISTANCE
    # Today must break above the past 10-day high
    if close <= past_10_high:
        return {"passed": False, "reasons": ["No breakout above consolidation"]}
        
    # 9. EXTENSION
    if close > past_10_high * 1.05:
        return {"passed": False, "reasons": ["Overextended breakout (>5%)"]}
        
    # 4. VOLATILITY CONTRACTION
    atr = (df['High'] - df['Low']).rolling(14).mean()
    current_atr = atr.iloc[-1]
    avg_atr_past = atr.iloc[-11:-1].mean()
    if current_atr > avg_atr_past:
        return {"passed": False, "reasons": ["ATR not declining"]}
        
    # 6. MOMENTUM
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if rsi <= 55:
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} too low (<=55)"]}
        
    macd, macdsignal, _ = talib.MACD(df['Close'], fastperiod=12, slowperiod=26, signalperiod=9)
    if pd.isna(macd.iloc[-1]) or macd.iloc[-1] <= macdsignal.iloc[-1]:
        return {"passed": False, "reasons": ["MACD not improving"]}
        
    # 7. VOLUME
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if df['Volume'].iloc[-1] < vol_sma20 * 1.5:
        return {"passed": False, "reasons": ["Volume < 1.5x average"]}
        
    return {"passed": True, "score": 1.0, "trigger_type": "Volatility Compression Breakout"}

def relative_strength_eval(df, nifty_hist=None, sector_hist=None):
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
        
    close = df['Close'].iloc[-1]
    
    # 1. & 2. TRENDS
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    
    if not (close > sma200 and ema50 > sma200 and ema20 > ema50):
        return {"passed": False, "reasons": ["Trend not aligned"]}
        
    # 3. ABSOLUTE MOMENTUM
    close_20 = df['Close'].iloc[-21] if len(df) > 20 else df['Close'].iloc[0]
    close_60 = df['Close'].iloc[-61] if len(df) > 60 else df['Close'].iloc[0]
    
    ret_20 = (close - close_20) / close_20
    ret_60 = (close - close_60) / close_60
    
    if ret_20 <= 0 or ret_60 <= 0:
        return {"passed": False, "reasons": ["Negative absolute momentum"]}
        
    # 4. FACTOR STRIPPING (IDIOSYNCRATIC MOMENTUM)
    if nifty_hist is not None and sector_hist is not None and len(nifty_hist) > 60 and len(sector_hist) > 60:
        # Get daily returns as pandas Series to preserve date index
        stock_ret = df['Close'].pct_change().fillna(0)
        nifty_ret = nifty_hist['Close'].pct_change().fillna(0)
        sector_ret = sector_hist['Close'].pct_change().fillna(0)
        
        # Enforce strict date alignment to prevent forward bias (comparing misaligned days)
        aligned = pd.concat([stock_ret, nifty_ret, sector_ret], axis=1, join='inner').dropna()
        aligned = aligned.iloc[-60:]
        
        if len(aligned) < 30:
            return {"passed": False, "reasons": ["Not enough aligned dates for regression"]}
            
        # Regress Stock = Alpha + B1*Nifty + B2*Sector
        y = aligned.iloc[:, 0].values
        X = aligned.iloc[:, 1:3].values
        
        model = LinearRegression()
        model.fit(X, y)
        
        # Alpha is daily residual return. Multiply by window to get total 60-day alpha
        idiosyncratic_return = model.intercept_ * len(aligned)
        alpha_score = idiosyncratic_return
        
        if idiosyncratic_return <= 0.05: # Require at least 5% alpha over 60 days
            return {"passed": False, "reasons": [f"Low Idiosyncratic Momentum (Alpha: {idiosyncratic_return:.3f})"]}
    else:
        n_ret_20 = 0.0
        n_ret_60 = 0.0
        if nifty_hist is not None and len(nifty_hist) > 60:
            nifty_close_20 = nifty_hist['Close'].iloc[-21]
            nifty_close_60 = nifty_hist['Close'].iloc[-61]
            nifty_close = nifty_hist['Close'].iloc[-1]
            n_ret_20 = (nifty_close - nifty_close_20) / nifty_close_20
            n_ret_60 = (nifty_close - nifty_close_60) / nifty_close_60
            
        if ret_20 <= n_ret_20 or ret_60 <= n_ret_60:
            return {"passed": False, "reasons": ["Underperforming Nifty"]}
        alpha_score = (ret_60 - n_ret_60)  # Excess return as proxy
        
    # 5. RSI
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if not (55 <= rsi <= 80):
        return {"passed": False, "reasons": [f"RSI {rsi:.2f} not in (55, 80)"]}
        
    # 7. VOLUME (Ensure reasonable volume)
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-1]
    if df['Volume'].iloc[-1] < vol_sma20 * 0.8:
        return {"passed": False, "reasons": ["Low relative volume"]}
        
    # 8. AVOID EXTENSION
    if close > ema20 * 1.10:
        return {"passed": False, "reasons": ["Overextended >10% from 20 EMA"]}
        
    # 9. VOLATILITY
    atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
    if atr / close > 0.05:
        return {"passed": False, "reasons": ["ATR > 5%"]}
        
    return {"passed": True, "score": 1.0, "alpha_score": alpha_score, "trigger_type": "Relative Strength Momentum"}

def pocket_pivot_eval(df, nifty_hist=None, sector_hist=None):
    """
    Pocket Pivot Institutional Accumulation:
    Enters inside a consolidation base before the standard resistance breakout.
    Triggered when an up-day's volume exceeds the highest down-volume day of the prior 10 days,
    while price bounces off or consolidates near the 10, 20, or 50 EMA.
    """
    if len(df) < 200:
        return {"passed": False, "reasons": ["Not enough data for 200 SMA"]}
    if len(df) > 300:
        df = df.iloc[-300:]
    
    # 0. NIFTY REGIME FILTER (Avoid longs when overall market is correcting)
    if nifty_hist is not None and len(nifty_hist) > 50:
        nifty_ema50 = nifty_hist['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
        if nifty_hist['Close'].iloc[-1] < nifty_ema50:
            return {"passed": False, "reasons": ["Nifty below 50 EMA"]}

    close = df['Close'].iloc[-1]
    open_p = df['Open'].iloc[-1]
    high = df['High'].iloc[-1]
    low = df['Low'].iloc[-1]
    prev_close = df['Close'].iloc[-2]

    # 1. LONG-TERM TREND: Long-term uptrend intact
    sma200 = df['Close'].rolling(window=200).mean().iloc[-1]
    ema50 = df['Close'].ewm(span=50, adjust=False).mean().iloc[-1]
    ema20 = df['Close'].ewm(span=20, adjust=False).mean().iloc[-1]
    ema10 = df['Close'].ewm(span=10, adjust=False).mean().iloc[-1]

    if not (close > sma200 and ema50 > sma200):
        return {"passed": False, "reasons": ["Not long-term bullish (Close > 200 SMA & 50 EMA > 200 SMA)"]}

    # 2. PROXIMITY TO KEY MOVING AVERAGE (Inside consolidation / bounce off support)
    dist_10 = abs(close - ema10) / ema10
    dist_20 = abs(close - ema20) / ema20
    dist_50 = abs(close - ema50) / ema50
    min_dist = min(dist_10, dist_20, dist_50)

    if min_dist > 0.035:
        return {"passed": False, "reasons": ["Too far from key moving average (10, 20, or 50 EMA)"]}

    # Not over-extended (>5% above 20 EMA)
    if close > (ema20 * 1.05):
        return {"passed": False, "reasons": ["Extended >5% above 20 EMA"]}

    # 3. CONSTRUCTIVE BASE (Consolidating, not in a free fall)
    low_10d = df['Low'].iloc[-11:-1].min()
    if low_10d < ema50 * 0.95:
        return {"passed": False, "reasons": ["Broken down > 5% below 50 EMA in past 10 days"]}

    # 4. CANDLE PRICE ACTION: Must be a constructive up-day
    candle_range = high - low
    if candle_range == 0 or close <= prev_close or close < open_p:
        return {"passed": False, "reasons": ["Not a bullish up day"]}
    
    close_strength = (close - low) / candle_range
    if close_strength < 0.50:
        return {"passed": False, "reasons": ["Weak close (below candle midpoint)"]}

    # 5. POCKET PIVOT VOLUME SIGNATURE (Core Institutional Accumulation Rule)
    # Today's volume must exceed the HIGHEST down-volume day in the prior 10 days
    vol = df['Volume'].iloc[-1]
    vol_sma20 = df['Volume'].rolling(20).mean().iloc[-2]

    # Find down days in past 10 days (excluding today)
    past_10_closes = df['Close'].iloc[-11:-1].values
    past_10_prev_closes = df['Close'].iloc[-12:-2].values
    past_10_vols = df['Volume'].iloc[-11:-1].values

    down_mask = (past_10_closes < past_10_prev_closes)
    down_vols = past_10_vols[down_mask]

    highest_down_vol = down_vols.max() if len(down_vols) > 0 else 0

    if vol <= highest_down_vol:
        return {"passed": False, "reasons": [f"Volume ({vol}) did not exceed max down-volume ({highest_down_vol}) in last 10 days"]}

    if pd.notna(vol_sma20) and vol < (1.1 * vol_sma20):
        return {"passed": False, "reasons": ["Volume not > 1.1x 20d average"]}

    # 6. RELATIVE STRENGTH vs NIFTY
    if nifty_hist is not None and len(nifty_hist) >= 40 and len(df) >= 40:
        n_20 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-20]) - 1
        s_20 = (close / df['Close'].iloc[-21]) - 1
        if s_20 < n_20:
            return {"passed": False, "reasons": ["20d return lagging NIFTY"]}

    # 7. MOMENTUM CONFIRMATION (RSI)
    rsi = talib.RSI(df['Close'], timeperiod=14).iloc[-1]
    if pd.isna(rsi) or not (45 <= rsi <= 68):
        return {"passed": False, "reasons": [f"RSI {rsi:.1f} not in (45, 68)"]}

    # Alpha score for ranking: combination of volume expansion + MA proximity + RSI
    vol_ratio = min(3.0, vol / (highest_down_vol + 1e-5)) / 3.0
    ma_proximity_score = 1.0 - (min_dist / 0.035)
    rsi_score = (rsi - 45) / 23.0
    alpha_score = (vol_ratio * 0.4) + (ma_proximity_score * 0.3) + (rsi_score * 0.3)

    return {"passed": True, "score": 1.0, "alpha_score": alpha_score, "trigger_type": "Pocket Pivot Accumulation"}

# Define strategies here.
STRATEGIES = [
    {
        "name": "Momentum Breakout",
        "trading_tools": [],
        "trading_filters": ["Require High Liquidity (>100k Vol)", "Require RR >= 1:2"],
        "risk_management": "ATR 1.5",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": momentum_breakout_eval
    },
    {
        "name": "Volatility Compression",
        "description": "NIFTY 500 stocks undergoing declining volatility and a tight 10-day consolidation before breaking out on high volume.",
        "trading_tools": [],
        "trading_filters": [
            "Require High Liquidity (>100k Vol)"
        ],
        "risk_management": "ATR 1.5",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": volatility_compression_eval
    },
    {
        "name": "Relative Strength",
        "description": "NIFTY 500 stocks that are significantly outperforming the broader market during a bullish regime, buying on minor consolidations.",
        "trading_tools": [],
        "trading_filters": [
            "Require High Liquidity (>100k Vol)"
        ],
        "risk_management": "ATR 2.0",
        "ai_logic_prompt": None,
        "ai_filter_prompt": None,
        "precompiled_eval_func": relative_strength_eval
    }
]

METRICS_DAYS = 90

def send_telegram_message(message: str):
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN_SWING_PORTFOLIO")
    chat_id = os.getenv("TELEGRAM_CHAT_ID_SWING")
    
    if not bot_token or not chat_id:
        logger.warning("Telegram Bot Token or Chat ID not found in .env. Skipping Telegram notification.")
        return
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        logger.info("Successfully sent Telegram notification.")
    except Exception as e:
        logger.error(f"Failed to send Telegram notification: {e}")

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            trades = json.load(f)
            # Backfill for backward compatibility
            for t in trades:
                if "entry_regime" not in t or t["entry_regime"] == "Unknown":
                    # Parse the entry date string back to a date object
                    try:
                        e_date = datetime.strptime(t["entry_date"], "%Y-%m-%d").date()
                        t["entry_regime"] = get_market_regime(e_date)
                    except Exception:
                        t["entry_regime"] = "Unknown"
                if "exit_regime" not in t: 
                    t["exit_regime"] = None
            return trades
    return []

def save_state(trades):
    with open(STATE_FILE, "w") as f:
        json.dump(trades, f, indent=4)


def record_live_signals(trades, signals, signal_timestamp):
    """Append the exact near-close signals emitted by ``run_live_screener``.

    This is intentionally a ledger operation.  It never recomputes a signal
    from finalized EOD data, which would make the forward test diverge from the
    3:15 PM strategy that was actually traded.
    """
    signal_time = pd.Timestamp(signal_timestamp)
    signal_date = signal_time.date().isoformat()
    added = 0
    for signal in signals:
        symbol = signal["symbol"]
        duplicate = any(
            trade["symbol"] == symbol
            and trade.get("signal_date") == signal_date
            and trade.get("status") == "OPEN"
            for trade in trades
        )
        if duplicate:
            continue
        entry_price = float(signal["entry_price"])
        trades.append({
            "trade_id": str(uuid.uuid4()),
            "strategy_name": signal["strategy_name"],
            "symbol": symbol,
            "signal_date": signal_date,
            "signal_timestamp": signal_time.isoformat(),
            "entry_date": signal_date,
            "entry_price": entry_price,
            "close_price": entry_price,
            "stop_loss": signal["stop_loss"],
            "target": signal["target"],
            "risk_pct": signal["risk_pct"],
            "alpha_score": signal["alpha_score"],
            "regime_state": signal["regime_state"],
            "entry_regime": f"E12_STATE_{signal['regime_state']}",
            "bcr": signal["bcr"],
            "breadth": signal["breadth"],
            "status": "OPEN",
            "exit_date": None,
            "exit_regime": None,
            "exit_price": None,
            "pnl_pct": None,
        })
        added += 1
    logger.info("Recorded %s exact 3:15 PM E12 signals for %s.", added, signal_date)
    return trades

def get_market_regime(as_of_date):
    bulk_data = fetch_bulk_history(["NIFTYBEES"], as_of_date, lookback_days=100)
    nifty = bulk_data.get("NIFTYBEES")
    if nifty is not None and not nifty.empty and len(nifty) >= 60:
        # Calculate benchmark returns globally
        close_0 = nifty['Close'].iloc[-1]
        close_20 = nifty['Close'].iloc[-21] if len(nifty) > 20 else nifty['Close'].iloc[0]
        close_60 = nifty['Close'].iloc[-61] if len(nifty) > 60 else nifty['Close'].iloc[0]
        BENCHMARK_RETURNS["20d"] = (close_0 - close_20) / close_20
        BENCHMARK_RETURNS["60d"] = (close_0 - close_60) / close_60
        
        sma_50 = nifty["Close"].rolling(50).mean()
        sma_50_diff = sma_50.diff()
        
        curr_close = nifty["Close"].iloc[-1]
        curr_sma50 = sma_50.iloc[-1]
        curr_sma50_diff = sma_50_diff.iloc[-1]
        
        if curr_close > curr_sma50 and curr_sma50_diff > 0:
            return "Bullish"
        elif curr_close < curr_sma50 and curr_sma50_diff < 0:
            return "Bearish"
        else:
            return "Choppy"
    return "Unknown"

def update_open_trades(trades, as_of_date):
    """
    Checks open trades against today's EOD data to see if they hit SL or Target.
    """
    open_trades = [t for t in trades if t["status"] == "OPEN"]
    if not open_trades:
        return trades
        
    logger.info(f"Checking {len(open_trades)} open trades against {as_of_date} data...")
    
    # We only need to fetch data for the symbols in open trades
    symbols = list(set([t["symbol"] for t in open_trades]))
    bulk_data = fetch_bulk_history(symbols, as_of_date, lookback_days=5)
    
    date_str = as_of_date.strftime("%Y-%m-%d")
    current_regime = get_market_regime(as_of_date)
    
    for t in open_trades:
        sym = t["symbol"]
        if sym in bulk_data and not bulk_data[sym].empty:
            df = bulk_data[sym]
            # Check the last row (today)
            today_high = df['High'].iloc[-1]
            today_low = df['Low'].iloc[-1]
            today_close = df['Close'].iloc[-1]
            
            # Simple check: did it hit stop loss or target today?
            # Note: We prioritize Stop Loss hit over Target hit on the same day for conservatism.
            if today_low <= t["stop_loss"]:
                t["status"] = "LOSS"
                t["exit_date"] = date_str
                t["exit_price"] = t["stop_loss"]
                t["exit_regime"] = current_regime
                t["pnl_pct"] = ((t["exit_price"] - t["entry_price"]) / t["entry_price"]) * 100
                logger.info(f"Trade {t['trade_id']} ({sym}) CLOSED at LOSS: {t['pnl_pct']:.2f}%")
            elif today_high >= t["target"]:
                t["status"] = "WIN"
                t["exit_date"] = date_str
                t["exit_price"] = t["target"]
                t["exit_regime"] = current_regime
                t["pnl_pct"] = ((t["exit_price"] - t["entry_price"]) / t["entry_price"]) * 100
                logger.info(f"Trade {t['trade_id']} ({sym}) CLOSED at WIN: {t['pnl_pct']:.2f}%")
            else:
                # Fix 3: Time-based exit
                from src.screener.pipeline.swing.e12_strategy import MAX_HOLDING_SESSIONS
                from datetime import datetime
                import numpy as np
                entry_dt = datetime.strptime(t.get("entry_date", date_str), "%Y-%m-%d")
                # Approximate trading days (business days) since entry
                days_held = np.busday_count(entry_dt.date(), as_of_date.date())
                if days_held >= MAX_HOLDING_SESSIONS:
                    t["status"] = "TIMESTOP"
                    t["exit_date"] = date_str
                    t["exit_price"] = today_close
                    t["exit_regime"] = current_regime
                    t["pnl_pct"] = ((t["exit_price"] - t["entry_price"]) / t["entry_price"]) * 100
                    logger.info(f"Trade {t['trade_id']} ({sym}) CLOSED at TIMESTOP ({days_held} days): {t['pnl_pct']:.2f}%")
                    
    return trades

def run_strategies(trades, as_of_date):
    """
    Deprecated: new entries must come from the 3:15 PM live screener.

    STATE 1 — TREND      (BCR > 52%):                RS Alpha primary + Momentum Confirmation
    STATE 2 — MEAN-REVERT (BCR ≤ 52%, breadth ≥ 30%): Oversold Uptrend + Trend Pullback
    STATE 3 — CASH        (BCR ≤ 52%, breadth < 30%):  No new entries

    All regime inputs use strictly historical data — no forward bias.
    """
    raise RuntimeError(
        "run_strategies is disabled to prevent final-EOD rescans from diverging "
        "from run_live_screener's 3:15 PM E12 signals. Use record_live_signals instead."
    )
    import talib

    BCR_THRESHOLD = 0.52    # Momentum must beat coin flip to enter trend mode
    BREADTH_THRESHOLD = 0.30  # <30% stocks above SMA50 = extreme weakness → cash

    date_str = as_of_date.strftime("%Y-%m-%d")
    current_regime = get_market_regime(as_of_date)

    logger.info("Loading NIFTY 500 universe...")
    symbols = load_nifty500_symbols()
    if "NIFTYBEES" not in symbols:
        symbols.append("NIFTYBEES")

    logger.info(f"Fetching bulk history up to {date_str}...")
    bulk_data = fetch_bulk_history(symbols, end_date=as_of_date, lookback_days=300)

    nifty_hist = bulk_data.pop("NIFTYBEES") if "NIFTYBEES" in bulk_data else None

    # --- BCR: Breakout Continuation Rate (lookback 120→30 days ago, 20-day outcomes) ---
    breakout_events = []
    for sym, df in bulk_data.items():
        if len(df) < 60:
            continue
        high_40 = df['High'].rolling(40).max().shift(1)
        cutoff_end = pd.Timestamp(as_of_date) - pd.Timedelta(days=30)
        cutoff_start = pd.Timestamp(as_of_date) - pd.Timedelta(days=140)
        mask = (df.index >= cutoff_start) & (df.index <= cutoff_end)
        for pos_idx in df.index[mask]:
            pos = df.index.get_loc(pos_idx)
            if pos + 20 >= len(df):
                continue
            if pd.notna(high_40.iloc[pos]) and df['Close'].iloc[pos] > high_40.iloc[pos]:
                entry_p = df['Close'].iloc[pos]
                future_p = df['Close'].iloc[pos + 20]
                breakout_events.append(1 if future_p > entry_p else 0)
    bcr = sum(breakout_events) / len(breakout_events) if len(breakout_events) >= 10 else 0.5

    # --- Breadth: % stocks with Close > SMA50 today ---
    above = sum(
        1 for df in bulk_data.values()
        if len(df) >= 50
        and pd.notna(df['Close'].rolling(50).mean().iloc[-1])
        and df['Close'].iloc[-1] > df['Close'].rolling(50).mean().iloc[-1]
    )
    total_valid = sum(1 for df in bulk_data.values() if len(df) >= 50)
    breadth = above / total_valid if total_valid > 0 else 0.5

    # --- Determine regime state ---
    if bcr > BCR_THRESHOLD:
        regime_state = 1
        primary_func = volatility_compression_eval
        confirm_func = trend_pullback_eval
        signal_label = "E12-Trend"
        logger.info(f"Regime STATE 1 — TREND (BCR={bcr:.3f}). Using Volatility Compression + Trend Pullback.")
    elif breadth < BREADTH_THRESHOLD:
        regime_state = 3
        logger.info(f"Regime STATE 3 — CASH PRESERVATION (BCR={bcr:.3f}, Breadth={breadth:.1%}). No new entries.")
        return trades  # Existing positions managed by update_open_trades — no new entries
    else:
        regime_state = 2
        primary_func = trend_pullback_eval
        confirm_func = oversold_uptrend_eval
        signal_label = "E12-MeanRev"
        logger.info(f"Regime STATE 2 — MEAN-REVERT (BCR={bcr:.3f}, Breadth={breadth:.1%}). Using Trend Pullback + Oversold Uptrend.")

    # --- Build sector indices ---
    from src.data.nse_fetcher import load_nifty500_industry_mapping
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

    # --- Evaluate all symbols ---
    all_candidates = []
    for symbol, df in bulk_data.items():
        df = df[df.index <= pd.Timestamp(as_of_date)]
        if len(df) < 200:
            continue
        try:
            sector_hist = None
            if symbol in industry_mapping:
                ind = industry_mapping[symbol]
                if ind in sector_indices:
                    sector_hist = sector_indices[ind][sector_indices[ind].index <= pd.Timestamp(as_of_date)]

            p_res = primary_func(df, nifty_hist=nifty_hist, sector_hist=sector_hist)
            if not p_res or not p_res.get("passed"):
                continue

            try:
                c_res = confirm_func(df, nifty_hist=nifty_hist, sector_hist=sector_hist)
            except:
                c_res = None

            confirmed = c_res and c_res.get("passed")
            close_price = df['Close'].iloc[-1]
            atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
            if pd.isna(atr) or atr <= 0:
                continue

            stop_loss = close_price - (2.0 * atr)
            target = close_price + (4.0 * atr)
            alpha_score = p_res.get("alpha_score", 0.0)
            strategy_name = f"{signal_label}-{'Confirmed' if confirmed else 'Primary'}"

            all_candidates.append({
                "strategy_name": strategy_name,
                "symbol": symbol,
                "tradingview_link": f"https://in.tradingview.com/chart/?symbol=NSE:{symbol}",
                "entry_date": date_str,
                "entry_regime": current_regime,
                "regime_state": regime_state,
                "bcr": round(bcr, 4),
                "breadth": round(breadth, 4),
                "entry_price": close_price,
                "close_price": close_price,
                "stop_loss": round(stop_loss, 2),
                "target": round(target, 2),
                "alpha_score": round(alpha_score, 4),
                "status": "OPEN",
                "exit_date": None,
                "exit_regime": None,
                "exit_price": None,
                "pnl_pct": None,
                "score": alpha_score
            })
        except Exception:
            pass

    # --- Rank by alpha score, take top 5 confirmed + top 5 primary-only ---
    confirmed_cands = sorted([c for c in all_candidates if "Confirmed" in c["strategy_name"]],
                              key=lambda x: x["score"], reverse=True)[:5]
    primary_cands = sorted([c for c in all_candidates if "Primary" in c["strategy_name"]],
                            key=lambda x: x["score"], reverse=True)[:5]
    top_candidates = confirmed_cands + primary_cands

    added = 0
    for c in top_candidates:
        already_open = any(
            t["symbol"] == c["symbol"] and t["status"] == "OPEN"
            for t in trades
        )
        if already_open:
            logger.info(f"Skipping {c['symbol']} — already have an OPEN trade.")
            continue
        c["trade_id"] = str(uuid.uuid4())
        trade_to_save = {k: v for k, v in c.items() if k != "score" and k != "pending_confirmation"}
        trades.append(trade_to_save)
        logger.info(f"Logged new OPEN trade: {c['symbol']} ({c['strategy_name']}) at {c['entry_price']:.2f}")
        added += 1

    logger.info(f"Added {added} new trades. Regime: State {regime_state}, BCR={bcr:.3f}, Breadth={breadth:.1%}")
    return trades

def calculate_metrics(trades):
    """
    Calculates performance metrics per strategy and writes to strategy-specific metrics.csv
    """
    strategy_names = list(set([t["strategy_name"] for t in trades]))
    
    for s_name in strategy_names:
        s_trades = [t for t in trades if t["strategy_name"] == s_name]
        closed_trades = [t for t in s_trades if t["status"] in ["WIN", "LOSS"]]
        
        total_trades = len(closed_trades)
        if total_trades == 0:
            continue
            
        wins = [t for t in closed_trades if t["status"] == "WIN"]
        losses = [t for t in closed_trades if t["status"] == "LOSS"]
        
        win_rate = (len(wins) / total_trades) * 100
        
        avg_win = sum([t["pnl_pct"] for t in wins]) / len(wins) if wins else 0.0
        avg_loss = sum([t["pnl_pct"] for t in losses]) / len(losses) if losses else 0.0
        
        # Max Drawdown calculation
        closed_trades.sort(key=lambda x: x["exit_date"])
        cumulative_pnl = 0
        peak = 0
        max_dd = 0
        
        for t in closed_trades:
            cumulative_pnl += t["pnl_pct"]
            if cumulative_pnl > peak:
                peak = cumulative_pnl
            dd = peak - cumulative_pnl
            if dd > max_dd:
                max_dd = dd
                
        metrics = [{
            "Strategy": s_name,
            "Total Closed Trades": total_trades,
            "Win Rate %": round(win_rate, 2),
            "Avg Win %": round(avg_win, 2),
            "Avg Loss %": round(avg_loss, 2),
            "Max Drawdown %": round(max_dd, 2)
        }]
        
        safe_name = s_name.replace(" ", "_").replace("/", "_")
        strat_dir = os.path.join(FRONT_TEST_DIR, safe_name)
        os.makedirs(strat_dir, exist_ok=True)
        metrics_file = os.path.join(strat_dir, "metrics.csv")
        
        keys = metrics[0].keys()
        with open(metrics_file, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, keys)
            dict_writer.writeheader()
            dict_writer.writerows(metrics)

def export_to_csv(trades):
    """
    Exports the trades into individual CSV files per strategy for easy user viewing.
    """
    if not trades:
        return
        
    strategy_names = list(set([t["strategy_name"] for t in trades]))
    
    for s_name in strategy_names:
        s_trades = [t for t in trades if t["strategy_name"] == s_name]
        
        if not s_trades:
            continue
            
        safe_name = s_name.replace(" ", "_").replace("/", "_")
        strat_dir = os.path.join(FRONT_TEST_DIR, safe_name)
        os.makedirs(strat_dir, exist_ok=True)
        csv_path = os.path.join(strat_dir, "trades.csv")
        
        # Sort trades by entry date descending
        s_trades.sort(key=lambda x: x["entry_date"], reverse=True)
        
        # Collect all unique keys across all trades to prevent missing field errors
        keys = list(s_trades[0].keys())
        for t in s_trades:
            for k in t.keys():
                if k not in keys:
                    keys.append(k)
                    
        with open(csv_path, 'w', newline='') as output_file:
            dict_writer = csv.DictWriter(output_file, fieldnames=keys)
            dict_writer.writeheader()
            dict_writer.writerows(s_trades)
            
        logger.info(f"Exported {len(s_trades)} trades to {csv_path}")

def main():
    if len(sys.argv) > 1:
        date_input = sys.argv[1]
    elif sys.stdin.isatty():
        date_input = input("Enter the date to run the screener for (YYYY-MM-DD) or press Enter for today: ").strip()
    else:
        date_input = ""
    
    if date_input:
        try:
            as_of_date = datetime.strptime(date_input, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid date format. Using today's date instead.")
            as_of_date = date.today()
    else:
        as_of_date = date.today()
    
    logger.info(f"--- Starting Forward Test Engine for requested date: {as_of_date} ---")
    
    trades = load_state()
    logger.info(f"Loaded {len(trades)} historical/open trades.")
    
    # 1. Update Open Trades
    trades = update_open_trades(trades, as_of_date)
    
    # New entries are recorded by run_live_screener at 3:15 PM.  Do not rescan
    # after close: that would use a different (final EOD) information set.
    
    # 3. Save State (JSON for machine readability)
    save_state(trades)
    
    # 4. Export individual CSVs for human viewing
    export_to_csv(trades)
    
    # 5. Calculate Metrics
    calculate_metrics(trades)
    
    # 6. Continuous Portfolio Tracking & Optimization
    date_str = as_of_date.strftime("%Y-%m-%d")
    
    e12_candidates = [
        trade for trade in trades
        if trade.get("entry_date") == date_str
        and trade.get("status") == "OPEN"
        and trade.get("strategy_name", "").startswith("E12-")
    ]
    try:
        from src.screener.portfolio.portfolio_tracker import step_portfolio
        step_portfolio(e12_candidates, as_of_date, strategy_name="E12_Three_State")
    except Exception as e:
        logger.error(f"Error during portfolio tracking/optimization for E12_Three_State: {e}")
        
    # Format and send Telegram Message
    tg_msg = f"<b>📊 Swing Portfolio Update (5:30 PM): {date_str} 📊</b>\n\n"
    
    closed_today = [t for t in trades if t.get('status') == 'CLOSED' and t.get('exit_date') == date_str]
    open_trades = [t for t in trades if t.get('status') == 'OPEN']
    
    tg_msg += "<b>🔴 CLOSED TRADES TODAY:</b>\n"
    if not closed_today:
        tg_msg += "No trades closed today.\n\n"
    else:
        for t in closed_today:
            pnl = t.get('pnl_pct')
            pnl = pnl if pnl is not None else 0
            emoji = "🟢" if pnl > 0 else "🔴"
            tg_msg += (
                f"• <b>{t['symbol']}</b> | {t.get('strategy_name', 'Unknown')}\n"
                f"  Exit Strategy: {t.get('exit_reason', 'Unknown')}\n"
                f"  PNL: {emoji} {pnl:.2f}%\n"
                f"  Holding Period: {t.get('holding_period_days', 0)} days\n\n"
            )
            
    tg_msg += "<b>💼 ACTIVE PORTFOLIO:</b>\n"
    if not open_trades:
        tg_msg += "No open positions.\n\n"
    else:
        for t in open_trades:
            pnl = t.get('pnl_pct')
            pnl = pnl if pnl is not None else 0
            emoji = "🟢" if pnl > 0 else "🔴"
            
            # Fallback for brand new trades where current_price hasn't updated yet
            curr_price = t.get('current_price')
            if not curr_price:
                curr_price = t.get('entry_price', 0)
                
            tg_msg += (
                f"• <b>{t['symbol']}</b> | {emoji} {pnl:.2f}%\n"
                f"  Entry: ₹{t.get('entry_price', 0):.2f} | Current: ₹{curr_price:.2f}\n"
                f"  SL: ₹{t.get('stop_loss', 0):.2f} | Target: ₹{t.get('target', 0):.2f}\n\n"
            )

    # Prevent message from exceeding telegram length limits
    if len(tg_msg) > 4000:
        tg_msg = tg_msg[:4000] + "\n...[Message Truncated]..."
        
    send_telegram_message(tg_msg)
    
    logger.info("--- Forward Test Engine Completed ---")
    cleanup_cache()

if __name__ == "__main__":
    main()
