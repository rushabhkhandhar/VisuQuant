import pandas as pd
import pandas_ta as ta
import numpy as np
from scipy.signal import argrelextrema

def sma(series: pd.Series, window: int) -> pd.Series:
    """Calculate Simple Moving Average."""
    return ta.sma(series, length=window)

def ema(series: pd.Series, window: int) -> pd.Series:
    """Calculate Exponential Moving Average."""
    return ta.ema(series, length=window)

def atr(df: pd.DataFrame, window: int) -> pd.Series:
    """
    Calculate Average True Range.
    Excludes circuit days by forward-filling the prior valid True Range 
    so the moving average isn't artificially dragged down by 0-range days.
    """
    prev_close = df['Close'].shift(1)
    tr1 = df['High'] - df['Low']
    tr2 = (df['High'] - prev_close).abs()
    tr3 = (df['Low'] - prev_close).abs()
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    if "is_circuit_day" in df.columns:
        # Mask circuit days as NaN and forward-fill the last valid True Range
        tr = tr.mask(df["is_circuit_day"] == True, np.nan).ffill()
        
    # ATR is the Wilder's Moving Average (RMA) of the True Range
    return ta.rma(tr, length=window)

def bollinger_bands(series: pd.Series, window: int = 20, num_std: float = 2.0, is_circuit_day: pd.Series = None) -> pd.DataFrame:
    """
    Calculate Bollinger Bands.
    Excludes circuit days from Bandwidth calculations by forward-filling 
    the prior valid band ranges.
    """
    bb = ta.bbands(series, length=window, std=num_std)
    if bb is None or bb.empty:
        # Return empty df with expected columns if ta fails
        return pd.DataFrame(columns=['BBL', 'BBM', 'BBU'])
        
    # pandas_ta returns columns like BBL_20_2.0, BBM_20_2.0, BBU_20_2.0
    # Let's standardize them
    bb = bb.rename(columns={
        bb.columns[0]: 'BBL',
        bb.columns[1]: 'BBM',
        bb.columns[2]: 'BBU'
    })[['BBL', 'BBM', 'BBU']]
    
    if is_circuit_day is not None:
        # Mask upper and lower bands on circuit days and ffill
        bb['BBL'] = bb['BBL'].mask(is_circuit_day == True, np.nan).ffill()
        bb['BBU'] = bb['BBU'].mask(is_circuit_day == True, np.nan).ffill()
        
    return bb

def rsi(series: pd.Series, window: int = 14) -> pd.Series:
    """Calculate Relative Strength Index."""
    return ta.rsi(series, length=window)

def macd(series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """Calculate MACD. Returns DataFrame with [MACD, Histogram, Signal]."""
    res = ta.macd(series, fast=fast, slow=slow, signal=signal)
    if res is None or res.empty:
        return pd.DataFrame(columns=['MACD', 'Histogram', 'Signal'])
        
    return res.rename(columns={
        res.columns[0]: 'MACD',
        res.columns[1]: 'Histogram',
        res.columns[2]: 'Signal'
    })[['MACD', 'Histogram', 'Signal']]

def rolling_52w_high(series: pd.Series) -> pd.Series:
    """Calculate rolling 52-week (approx 252 trading days) high."""
    return series.rolling(window=252, min_periods=1).max()

def find_swing_points(df: pd.DataFrame, order: int = 5) -> dict:
    """
    Detects swing highs and lows using scipy.signal.argrelextrema.
    Returns a dict with 'highs' and 'lows' containing the (date, price) tuples.
    """
    if df.empty or len(df) < (order * 2 + 1):
        return {"highs": [], "lows": []}
        
    high_idx = argrelextrema(df['High'].values, np.greater, order=order)[0]
    low_idx = argrelextrema(df['Low'].values, np.less, order=order)[0]
    
    highs = [(df.index[i], df['High'].iloc[i]) for i in high_idx]
    lows = [(df.index[i], df['Low'].iloc[i]) for i in low_idx]
    
    return {"highs": highs, "lows": lows}
