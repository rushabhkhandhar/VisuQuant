import pandas as pd
import numpy as np
from src.screener import config
from src.screener.indicators.core import bollinger_bands, ema

def bollinger_squeeze_breakout(df: pd.DataFrame, bb_lookback_months: int = config.BB_LOOKBACK_MONTHS, volume_mult: float = config.VOLUME_BREAKOUT_MULT) -> dict:
    """
    Detects a Bollinger Band squeeze breakout.
    - Squeeze: Bandwidth is in the bottom 10th percentile over the last 6 months.
    - Breakout: Close breaks upper band.
    - Volume: Breakout volume >= volume_mult * 20-day avg volume.
    """
    # 6 months of trading days is approximately 126 days
    lookback_days = bb_lookback_months * 21
    
    if "bollinger_breakout" in getattr(config, "DISABLED_TRIGGERS", []):
        return {"passed": False, "bandwidth": None, "bandwidth_pctile": None, "volume_ratio": None}
        
    if df.empty or len(df) < lookback_days + 20: # Need enough data for rolling metrics
        return {"passed": False, "bandwidth": None, "bandwidth_pctile": None, "volume_ratio": None}
        
    # Calculate Bollinger Bands
    # Pass is_circuit_day if it exists to avoid distorting BB logic
    is_circuit = df['is_circuit_day'] if 'is_circuit_day' in df.columns else None
    bb = bollinger_bands(df['Close'], window=20, num_std=2.0, is_circuit_day=is_circuit)
    
    # Calculate Bandwidth
    bandwidth = (bb['BBU'] - bb['BBL']) / bb['BBM']
    
    # Calculate 10th percentile threshold dynamically over the rolling window (avoids lookahead bias)
    # rolling().quantile() natively computes the 10th percentile strictly up to the current row
    rolling_10th_pctile = bandwidth.rolling(window=lookback_days).quantile(0.10)
    
    # Alternatively, get the exact percentile rank of the current bandwidth
    def get_percentile_rank(x):
        return (x <= x.iloc[-1]).sum() / len(x)
        
    # Calculate volume ratio
    avg_vol_20d = df['Volume'].rolling(20).mean()
    vol_ratio = df['Volume'] / avg_vol_20d
    
    # Get latest row
    curr_close = df['Close'].iloc[-1]
    curr_bbu = bb['BBU'].iloc[-1]
    curr_bandwidth = bandwidth.iloc[-1]
    prev_bandwidth = bandwidth.iloc[-2]  # Squeeze must exist BEFORE the breakout candle
    curr_vol_ratio = vol_ratio.iloc[-1]
    
    # Current percentile rank of yesterday's bandwidth
    window_bandwidth = bandwidth.iloc[-lookback_days-1:-1]
    if len(window_bandwidth) > 0 and not pd.isna(prev_bandwidth):
        current_pctile_rank = (window_bandwidth < prev_bandwidth).sum() / len(window_bandwidth)
    else:
        current_pctile_rank = 1.0
        
    # Condition 1: Squeeze (bandwidth is in bottom 10th percentile of 6 month window)
    cond1 = current_pctile_rank <= 0.10
    
    # Condition 2: Breakout (latest close breaks upper band)
    cond2 = curr_close > curr_bbu
    
    # Condition 3: Volume confirmation
    cond3 = curr_vol_ratio >= volume_mult
    
    passed = bool(cond1 and cond2 and cond3)
    
    return {
        "passed": passed,
        "bandwidth": float(curr_bandwidth) if not pd.isna(curr_bandwidth) else None,
        "bandwidth_pctile": float(current_pctile_rank),
        "volume_ratio": float(curr_vol_ratio) if not pd.isna(curr_vol_ratio) else None,
        "is_squeeze": bool(cond1),
        "is_breakout": bool(cond2),
        "is_vol_confirmed": bool(cond3)
    }

def _is_hammer(o, h, l, c):
    body = abs(c - o)
    lower_shadow = min(o, c) - l
    upper_shadow = h - max(o, c)
    return (lower_shadow >= 2 * body) and (upper_shadow <= body) and (body > 0)

def _is_bullish_engulfing(prev_o, prev_c, o, c):
    prev_red = prev_c < prev_o
    curr_green = c > o
    engulfs = (o < prev_c) and (c > prev_o)
    return prev_red and curr_green and engulfs

def _is_morning_star(p2_o, p2_c, p1_o, p1_c, o, c):
    p2_red = p2_c < p2_o
    p2_body_mid = (p2_o + p2_c) / 2
    
    p1_body = abs(p1_c - p1_o)
    p2_body = abs(p2_c - p2_o)
    p1_small = p1_body < (p2_body * 0.5)
    p1_gap_down = max(p1_o, p1_c) < min(p2_o, p2_c)
    
    curr_green = c > o
    curr_closes_deep = c > p2_body_mid
    
    return p2_red and p1_small and (p1_gap_down or max(p1_o, p1_c) < p2_c) and curr_green and curr_closes_deep

def ma_pullback_bounce(df: pd.DataFrame) -> dict:
    """
    Detects a pullback bounce off the 50 EMA.
    - Confirms 20 EMA > 50 EMA > 200 EMA.
    - Detects if price touched/pierced 50 EMA in last 3 days and closed above it.
    - Reversal candlestick (Hammer, Bullish Engulfing, Morning Star) on the touch day.
    - Volume on reversal candle > 10-day average.
    """
    if df.empty or len(df) < 200:
        return {"passed": False, "reversal_type": None, "touch_day_index": None}
        
    ema20 = ema(df['Close'], 20)
    ema50 = ema(df['Close'], 50)
    ema200 = ema(df['Close'], 200)
    
    curr_ema20 = ema20.iloc[-1]
    curr_ema50 = ema50.iloc[-1]
    curr_ema200 = ema200.iloc[-1]
    curr_close = df['Close'].iloc[-1]
    
    if pd.isna(curr_ema200):
        return {"passed": False, "reversal_type": None, "touch_day_index": None}
        
    # Cond 1: 20 EMA > 50 EMA > 200 EMA
    cond1 = (curr_ema20 > curr_ema50) and (curr_ema50 > curr_ema200)
    
    # Cond 2: Touched/pierced 50 EMA in last 3 candles, and currently closed above it
    if not cond1 or curr_close < curr_ema50:
        return {"passed": False, "reversal_type": None, "touch_day_index": None}
        
    avg_vol_10d = df['Volume'].rolling(10).mean()
    
    # Look back over the last 3 days
    # Day -1 is the current day, Day -2 is yesterday, Day -3 is day before yesterday
    touch_found = False
    reversal_type = None
    touch_day_idx = None
    
    for offset in [1, 2, 3]:
        idx = -offset
        try:
            o = df['Open'].iloc[idx]
            h = df['High'].iloc[idx]
            l = df['Low'].iloc[idx]
            c = df['Close'].iloc[idx]
            v = df['Volume'].iloc[idx]
            e50 = ema50.iloc[idx]
            v10 = avg_vol_10d.iloc[idx]
        except IndexError:
            continue
            
        # Touched or pierced: Low is below or equal to 50 EMA, but High is above 50 EMA
        if l <= e50 and h >= e50:
            # Check volume confirmation
            if v > v10:
                # Check reversal candles
                # 1. Hammer
                if "hammer" not in getattr(config, "DISABLED_TRIGGERS", []) and _is_hammer(o, h, l, c):
                    touch_found = True
                    reversal_type = "Hammer"
                    touch_day_idx = offset
                    break
                    
                # 2. Bullish Engulfing (needs prev day)
                if "bullish_engulfing" not in getattr(config, "DISABLED_TRIGGERS", []) and len(df) >= offset + 1:
                    prev_o = df['Open'].iloc[idx - 1]
                    prev_c = df['Close'].iloc[idx - 1]
                    if _is_bullish_engulfing(prev_o, prev_c, o, c):
                        touch_found = True
                        reversal_type = "Bullish Engulfing"
                        touch_day_idx = offset
                        break
                        
                # 3. Morning Star (needs prev 2 days)
                if "morning_star" not in getattr(config, "DISABLED_TRIGGERS", []) and len(df) >= offset + 2:
                    p2_o = df['Open'].iloc[idx - 2]
                    p2_c = df['Close'].iloc[idx - 2]
                    p1_o = df['Open'].iloc[idx - 1]
                    p1_c = df['Close'].iloc[idx - 1]
                    if _is_morning_star(p2_o, p2_c, p1_o, p1_c, o, c):
                        touch_found = True
                        reversal_type = "Morning Star"
                        touch_day_idx = offset
                        break
                        
    passed = bool(cond1 and touch_found)
    
    return {
        "passed": passed,
        "reversal_type": reversal_type,
        "touch_day_ago": touch_day_idx
    }
