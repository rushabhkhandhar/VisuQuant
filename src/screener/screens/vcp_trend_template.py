import pandas as pd
from src.screener.indicators.core import sma, atr, rolling_52w_high
from src.screener import config

def evaluate_vcp_trend(df: pd.DataFrame, near_52w_high_pct: float = config.NEAR_52W_HIGH_PCT) -> dict:
    """
    Minervini-style trend template and Volatility Contraction Pattern (VCP) screen.
    Returns a dict with pass/fail and metrics for ranking.
    """
    # Requires at least 200 days of data for the 200 SMA
    if df.empty or len(df) < 200:
        return {"passed": False, "atr_ratio": None, "pct_from_high": None, "trend_up_days": 0}
        
    # 1. Compute indicators
    sma50 = sma(df['Close'], 50)
    sma150 = sma(df['Close'], 150)
    sma200 = sma(df['Close'], 200)
    
    atr10 = atr(df, 10)
    atr50 = atr(df, 50)
    
    high_52w = rolling_52w_high(df['High'])
    
    # Extract latest scalar values
    current_close = df['Close'].iloc[-1]
    curr_sma50 = sma50.iloc[-1]
    curr_sma150 = sma150.iloc[-1]
    curr_sma200 = sma200.iloc[-1]
    
    curr_atr10 = atr10.iloc[-1]
    curr_atr50 = atr50.iloc[-1]
    curr_high_52w = high_52w.iloc[-1]
    
    if pd.isna(curr_sma200) or pd.isna(curr_atr50) or pd.isna(curr_high_52w):
        return {"passed": False, "atr_ratio": None, "pct_from_high": None, "trend_up_days": 0}
        
    # Condition 1: Close > 50 SMA > 150 SMA > 200 SMA
    cond1 = (current_close > curr_sma50) and (curr_sma50 > curr_sma150) and (curr_sma150 > curr_sma200)
    
    # Condition 2: 200 SMA has been trending up for at least the last 20 trading days
    # (i.e. monotonically increasing or at least higher than 20 days ago, we check rigorous consecutive up days)
    sma200_diff = sma200.diff().tail(60) # check up to 60 days back
    trend_up_days = 0
    for val in reversed(sma200_diff):
        if val > 0:
            trend_up_days += 1
        else:
            break
            
    cond2 = trend_up_days >= 20
    
    # Condition 3: Close is within NEAR_52W_HIGH_PCT of 52-week high
    pct_from_high = (curr_high_52w - current_close) / curr_high_52w
    cond3 = pct_from_high <= near_52w_high_pct
    
    # Condition 4: ATR(10) / ATR(50) ratio is below a contraction threshold (e.g. < 0.75)
    atr_ratio = curr_atr10 / curr_atr50 if curr_atr50 > 0 else 1.0
    cond4 = atr_ratio < 0.75
    
    # Condition 5: Average down-day volume over the last 10 days is below the 20-day average volume
    prev_close = df['Close'].shift(1)
    is_down_day = df['Close'] < prev_close
    
    last_10_down_vols = df['Volume'].tail(10)[is_down_day.tail(10)]
    avg_down_vol_10d = last_10_down_vols.mean() if not last_10_down_vols.empty else 0
    avg_vol_20d = df['Volume'].tail(20).mean()
    
    cond5 = avg_down_vol_10d < avg_vol_20d
    
    passed = bool(cond1 and cond2 and cond3 and cond4 and cond5)
    
    return {
        "passed": passed,
        "atr_ratio": float(atr_ratio),
        "pct_from_high": float(pct_from_high),
        "trend_up_days": trend_up_days
    }
