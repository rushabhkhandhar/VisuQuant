import pytest
import pandas as pd
import numpy as np
from src.screener.indicators.core import sma, ema, atr, bollinger_bands, rsi, macd, rolling_52w_high, find_swing_points

@pytest.fixture
def synthetic_data():
    dates = pd.date_range(start="2026-01-01", periods=20, freq="B")
    
    # Create a simple trend for deterministic testing
    df = pd.DataFrame({
        "Open": np.linspace(10, 29, 20),
        "High": np.linspace(12, 31, 20),
        "Low": np.linspace(8, 27, 20),
        "Close": np.linspace(11, 30, 20),
        "is_circuit_day": [False] * 20
    }, index=dates)
    
    # Insert a circuit day at index 10 (Day 11)
    df.loc[df.index[10], "High"] = df.loc[df.index[10], "Low"]
    df.loc[df.index[10], "is_circuit_day"] = True
    
    return df

def test_sma(synthetic_data):
    # SMA of [11, 12, 13] is 12
    res = sma(synthetic_data['Close'], window=3)
    assert not pd.isna(res.iloc[2])
    assert res.iloc[2] == 12.0

def test_ema(synthetic_data):
    res = ema(synthetic_data['Close'], window=3)
    assert not pd.isna(res.iloc[-1])
    
def test_atr(synthetic_data):
    # TR normally is High - Low (4.0).
    # Circuit day TR should be ffilled to 4.0, instead of 0.0.
    res = atr(synthetic_data, window=5)
    assert not pd.isna(res.iloc[-1])

def test_bollinger_bands(synthetic_data):
    bb = bollinger_bands(synthetic_data['Close'], window=5, num_std=2.0, is_circuit_day=synthetic_data['is_circuit_day'])
    assert 'BBL' in bb.columns and 'BBU' in bb.columns
    assert not bb['BBU'].isna().all()

def test_rsi(synthetic_data):
    res = rsi(synthetic_data['Close'], window=14)
    assert not pd.isna(res.iloc[-1])

def test_macd(synthetic_data):
    # Need 34 periods for MACD, our fixture has 20, let's test length requirements
    res = macd(synthetic_data['Close'], fast=3, slow=5, signal=3)
    assert 'MACD' in res.columns
    assert not res['MACD'].isna().all()

def test_rolling_52w_high(synthetic_data):
    res = rolling_52w_high(synthetic_data['High'])
    assert res.iloc[0] == 12.0
    assert res.iloc[-1] == 31.0

def test_find_swing_points():
    dates = pd.date_range(start="2026-01-01", periods=11, freq="B")
    # Peak at index 5 (value 20), trough at index 8 (value 5)
    highs = [10, 12, 14, 16, 18, 20, 18, 16, 14, 15, 16]
    lows  = [8,  10, 12, 14, 16, 15, 10,  7,  5,  8,  9]
    
    df = pd.DataFrame({"High": highs, "Low": lows}, index=dates)
    
    swings = find_swing_points(df, order=2)
    assert len(swings['highs']) >= 1
    assert len(swings['lows']) >= 1
    assert swings['highs'][0][1] == 20
    assert swings['lows'][0][1] == 5
