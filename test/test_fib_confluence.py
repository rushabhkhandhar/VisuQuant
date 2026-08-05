import pytest
import pandas as pd
import numpy as np
from src.screener.screens.fib_confluence import score_fib_confluence

def test_score_fib_confluence_uptrend_pocket():
    # Construct a synthetic upswing and pullback
    dates = pd.date_range(start="2026-01-01", periods=30, freq="B")
    
    # Days 1-10: Consolidation around 100
    prices = [100.0] * 10
    
    # Days 11-15: Rally from 100 to 200 (Swing Low -> Swing High)
    prices += [120, 140, 160, 180, 200]
    
    # Days 16-20: Pullback. 
    # The 0.5 level is 150. The 0.618 level is 138.2.
    # We want it to bottom at 145 (inside the golden pocket).
    prices += [190, 170, 155, 145, 160]
    
    # Days 21-30: Consolidating near the pocket
    prices += [148, 150, 149, 151, 147, 150, 148, 152, 149, 150]
    
    df = pd.DataFrame({
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Close": prices,
        "Volume": [1000] * 30
    }, index=dates)
    
    # For the 200 -> 145 downswing:
    # Diff = 55.
    # 0.5 level = 145 + 27.5 = 172.5
    # 0.618 level = 145 + 33.99 = 178.99
    # So the golden pocket is [172.5, 178.99]
    
    # We will make the recent bars rally up to exactly 175, testing the downtrend pocket!
    df = pd.DataFrame({
        "Open": prices,
        "High": prices,
        "Low": prices,
        "Close": prices,
        "Volume": [1000] * 30
    }, index=dates)
    
    # Ensure there is a distinct High at 200 (index 14) and distinct Low at 145 (index 18)
    
    # After the low at 145 (day 19), let's create a rally up to 175
    # Day 21-30
    rally_prices = [150, 160, 170, 175, 170, 165, 160, 160, 160, 160]
    for i, p in enumerate(rally_prices):
        df.loc[df.index[20 + i], ["Open", "High", "Low", "Close"]] = p
        
    res = score_fib_confluence(df, min_swing_magnitude_pct=0.10)
    
    assert res["in_golden_pocket"] is True
    assert res["swing_p1_type"] == "low"
    assert res["swing_p1_price"] == 145.0
    assert res["swing_p2_price"] == 175.0
    assert abs(res["pullback_extreme"] - 160.0) < 0.1
