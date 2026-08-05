import pytest
import pandas as pd
import numpy as np
from src.screener.screens.trigger_layer import bollinger_squeeze_breakout, ma_pullback_bounce

def test_bollinger_squeeze_breakout():
    # Need 146 days minimum (126 for rolling pctile + 20 for BB)
    dates = pd.date_range(start="2025-01-01", periods=200, freq="B")
    
    # Create flat data to establish a very tight Bollinger Band (squeeze)
    df = pd.DataFrame({
        "Open": [100.0] * 200,
        "High": [101.0] * 200,
        "Low": [99.0] * 200,
        "Close": [100.0] * 200,
        "Volume": [1000] * 200
    }, index=dates)
    
    # Now simulate a breakout on the last day
    df.loc[df.index[-1], "Close"] = 105.0
    df.loc[df.index[-1], "High"] = 106.0
    df.loc[df.index[-1], "Volume"] = 5000  # 5x volume breakout
    
    res = bollinger_squeeze_breakout(df, bb_lookback_months=6, volume_mult=2.5)
    
    assert res["passed"] is True
    assert res["is_squeeze"] is True
    assert res["is_breakout"] is True
    assert res["is_vol_confirmed"] is True

def test_ma_pullback_bounce():
    dates = pd.date_range(start="2025-01-01", periods=200, freq="B")
    
    # Create an uptrend so EMA 20 > EMA 50 > EMA 200
    close_prices = np.linspace(50, 150, 200)
    df = pd.DataFrame({
        "Open": close_prices,
        "High": close_prices + 2,
        "Low": close_prices - 2,
        "Close": close_prices,
        "Volume": [1000] * 200
    }, index=dates)
    
    # Check baseline (should fail because no touch)
    res = ma_pullback_bounce(df)
    assert res["passed"] is False
    
    # We need to manually construct a hammer on the last day that pierces the EMA50
    # The EMA 50 on the last day will be roughly 145 based on our linear trend
    # Let's mock the EMAs directly to be precise, or just construct the candle carefully.
    
    # Let's mock EMA50 to be exactly 140 on the last day
    # Hammer shape: Open=145, Close=148, Low=130 (pierces 140), High=149
    # Lower shadow = 145 - 130 = 15. Body = 3. 15 >= 6 (2 * body). True!
    # Upper shadow = 149 - 148 = 1. <= 3. True!
    
    df.loc[df.index[-1], "Open"] = 145.0
    df.loc[df.index[-1], "Close"] = 148.0
    df.loc[df.index[-1], "Low"] = 130.0
    df.loc[df.index[-1], "High"] = 149.0
    df.loc[df.index[-1], "Volume"] = 5000 # High volume
    
    # Run test with patching ema to control the environment perfectly
    from unittest.mock import patch
    
    # We will mock the EMA function inside trigger_layer
    with patch('src.screener.screens.trigger_layer.ema') as mock_ema:
        # Create mock EMA series
        mock_ema20 = pd.Series([150.0] * 200, index=dates)
        mock_ema50 = pd.Series([140.0] * 200, index=dates)
        mock_ema200 = pd.Series([100.0] * 200, index=dates)
        
        def side_effect(series, window):
            if window == 20: return mock_ema20
            elif window == 50: return mock_ema50
            elif window == 200: return mock_ema200
            
        mock_ema.side_effect = side_effect
        
        res = ma_pullback_bounce(df)
        
        assert res["passed"] is True
        assert res["reversal_type"] == "Hammer"
        assert res["touch_day_ago"] == 1
