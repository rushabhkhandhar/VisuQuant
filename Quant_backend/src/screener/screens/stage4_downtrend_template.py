import pandas as pd
from src.screener.indicators.core import sma, atr

def rolling_52w_low(series: pd.Series) -> pd.Series:
    """Returns the rolling 252-day (approx 52 weeks) minimum."""
    return series.rolling(window=252, min_periods=252).min()

def evaluate_stage4_downtrend(df: pd.DataFrame, near_52w_low_pct: float = 0.25) -> dict:
    """
    Inverted Stage 4 Downtrend Template.
    Returns a dict with pass/fail and metrics for ranking.
    """
    # Requires at least 200 days of data for the 200 SMA
    if df.empty or len(df) < 200:
        return {"passed": False, "atr_ratio": None, "pct_from_low": None, "trend_down_days": 0}
        
    # 1. Compute indicators
    sma50 = sma(df['Close'], 50)
    sma150 = sma(df['Close'], 150)
    sma200 = sma(df['Close'], 200)
    
    atr10 = atr(df, 10)
    atr50 = atr(df, 50)
    
    low_52w = rolling_52w_low(df['Low'])
    
    # Extract latest scalar values
    current_close = df['Close'].iloc[-1]
    curr_sma50 = sma50.iloc[-1]
    curr_sma150 = sma150.iloc[-1]
    curr_sma200 = sma200.iloc[-1]
    
    curr_atr10 = atr10.iloc[-1]
    curr_atr50 = atr50.iloc[-1]
    curr_low_52w = low_52w.iloc[-1]
    
    if pd.isna(curr_sma200) or pd.isna(curr_atr50) or pd.isna(curr_low_52w):
        return {"passed": False, "atr_ratio": None, "pct_from_low": None, "trend_down_days": 0}
        
    # Condition 1: Close < 50 SMA < 150 SMA < 200 SMA
    cond1 = (current_close < curr_sma50) and (curr_sma50 < curr_sma150) and (curr_sma150 < curr_sma200)
    
    # Condition 2: 200 SMA has been trending down for at least the last 20 trading days
    sma200_diff = sma200.diff().tail(60).values
    trend_down_days = 0
    for val in reversed(sma200_diff):
        if val < 0:
            trend_down_days += 1
        else:
            break
            
    cond2 = trend_down_days >= 20
    
    # Condition 3: Close is within near_52w_low_pct of 52-week low
    # e.g., if low is 100, price must be <= 125
    pct_from_low = (current_close - curr_low_52w) / curr_low_52w if curr_low_52w > 0 else 1.0
    cond3 = pct_from_low <= near_52w_low_pct
    
    # ATR contraction logic
    atr_ratio = curr_atr10 / curr_atr50 if curr_atr50 > 0 else 1.0
    
    passed = bool(cond1 and cond2 and cond3)
    
    return {
        "passed": passed,
        "atr_ratio": float(atr_ratio),
        "pct_from_low": float(pct_from_low),
        "trend_down_days": trend_down_days,
        "c1_sma": bool(cond1),
        "c2_sma200_down": bool(cond2),
        "c3_52w_low": bool(cond3)
    }
