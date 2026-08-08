import pandas as pd
import numpy as np
from src.screener import config


def _compute_rsi(series: pd.Series, period: int) -> pd.Series:
    """Compute RSI using exponential moving average (Wilder's method)."""
    delta = series.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = (-delta).where(delta < 0, 0.0)
    
    avg_gain = gain.ewm(alpha=1.0/period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1.0/period, min_periods=period).mean()
    
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100.0 - (100.0 / (1.0 + rs))
    return rsi


def _compute_streak(series: pd.Series) -> pd.Series:
    """
    Compute consecutive up/down streak.
    Positive = consecutive up days, Negative = consecutive down days.
    """
    diff = series.diff()
    streak = pd.Series(0, index=series.index, dtype=float)
    
    for i in range(1, len(series)):
        if diff.iloc[i] > 0:
            streak.iloc[i] = max(streak.iloc[i-1], 0) + 1
        elif diff.iloc[i] < 0:
            streak.iloc[i] = min(streak.iloc[i-1], 0) - 1
        else:
            streak.iloc[i] = 0
            
    return streak


def _compute_percent_rank(series: pd.Series, period: int) -> pd.Series:
    """
    Compute the percentile rank of the latest value within a rolling window.
    Returns 0-100 scale.
    """
    def pct_rank(x):
        if len(x) < 2:
            return 50.0
        last = x.iloc[-1]
        return (x.iloc[:-1] < last).sum() / (len(x) - 1) * 100.0
    
    return series.rolling(window=period, min_periods=period).apply(pct_rank, raw=False)


def compute_connors_rsi(df: pd.DataFrame) -> pd.Series:
    """
    ConnorsRSI = Average of three components:
      1. RSI(Close, 3)       — ultra-responsive price RSI
      2. RSI(Streak, 2)      — RSI of the up/down streak length
      3. PercentRank(ROC, 100) — percentile rank of today's return over 100 days
      
    Returns a Series of ConnorsRSI values (0-100 scale).
    """
    rsi_period = config.CONNORS_RSI_PERIOD
    streak_period = config.CONNORS_STREAK_PERIOD
    pctrank_period = config.CONNORS_PCTRANK_PERIOD
    
    close = df['Close']
    
    # Component 1: RSI of Close (3-period)
    rsi_close = _compute_rsi(close, rsi_period)
    
    # Component 2: RSI of Streak (2-period)
    streak = _compute_streak(close)
    rsi_streak = _compute_rsi(streak, streak_period)
    
    # Component 3: Percentile Rank of 1-day ROC over 100 days
    roc_1d = close.pct_change()
    pct_rank = _compute_percent_rank(roc_1d, pctrank_period)
    
    # ConnorsRSI = simple average of all three
    connors_rsi = (rsi_close + rsi_streak + pct_rank) / 3.0
    
    return connors_rsi


def connors_rsi_pullback(df: pd.DataFrame, disabled_triggers: list = None) -> dict:
    """
    ConnorsRSI Mean-Reversion Pullback Signal.
    
    Signal: Buy when ConnorsRSI drops below CONNORS_RSI_OVERSOLD (default: 10)
    within a stock that has already passed the VCP Trend Template (Stage 1).
    
    This catches short-term oversold dips within strong uptrends — high frequency,
    high win rate (~65-70%), short holding period (3-7 days).
    """
    if disabled_triggers is None:
        disabled_triggers = []
        
    if "connors_rsi_pullback" in disabled_triggers:
        return {"passed": False, "connors_rsi": None, "signal_type": None}
    
    min_data = config.CONNORS_PCTRANK_PERIOD + 10  # Need enough for percentile rank
    if df.empty or len(df) < min_data:
        return {"passed": False, "connors_rsi": None, "signal_type": None}
    
    crsi = compute_connors_rsi(df)
    
    curr_crsi = crsi.iloc[-1]
    
    if pd.isna(curr_crsi):
        return {"passed": False, "connors_rsi": None, "signal_type": None}
    
    # Check if the current ConnorsRSI is oversold (pullback within uptrend)
    is_oversold = curr_crsi <= config.CONNORS_RSI_OVERSOLD
    
    passed = bool(is_oversold)
    
    return {
        "passed": passed,
        "connors_rsi": float(curr_crsi),
        "signal_type": "Pullback Buy" if passed else None
    }
