import pytest
import pandas as pd
import numpy as np
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.screener.indicators.core import find_swing_points
from src.screener.screens.fib_confluence import get_golden_pocket

def create_synthetic_data():
    """
    Create a 30-day synthetic price series.
    Low at day 5 (price = 100)
    High at day 15 (price = 150)
    Pullback at day 22 (price = 120)
    """
    dates = pd.date_range("2026-01-01", periods=30, freq="B")
    
    # Base price 125
    prices = np.full(30, 125.0)
    
    # Create the swing low at day 5 (index 4)
    prices[0:5] = np.linspace(125, 100, 5)
    
    # Create the swing high at day 15 (index 14)
    prices[5:15] = np.linspace(105, 150, 10)
    
    # Create pullback at day 22 (index 21)
    prices[15:22] = np.linspace(145, 120, 7)
    
    # Bounce
    prices[22:30] = np.linspace(122, 135, 8)
    
    df = pd.DataFrame({
        "Open": prices,
        "High": prices + 2,
        "Low": prices - 2,
        "Close": prices,
        "Volume": 1000000
    }, index=dates)
    
    return df

def test_find_swing_points_lookahead():
    df = create_synthetic_data()
    
    # The high is at index 14. 
    # To confirm the high with order=5, we need at least 5 bars after index 14, 
    # which means up to index 19.
    
    # If as_of_date is index 16, the high at 14 should NOT be returned!
    as_of_date_unconfirmed = df.index[16]
    swings = find_swing_points(df, as_of_date=as_of_date_unconfirmed, order=5)
    
    # Check if any swing is at index 14
    for swing in swings:
        assert swing[0] != df.index[14], "Lookahead bias! High was returned before confirmation."
        
    # If as_of_date is index 19 (14 + 5), the high at 14 SHOULD be returned!
    as_of_date_confirmed = df.index[19]
    swings_confirmed = find_swing_points(df, as_of_date=as_of_date_confirmed, order=5)
    
    high_found = False
    for swing in swings_confirmed:
        if swing[0] == df.index[14]:
            high_found = True
            break
            
    assert high_found, "Confirmed swing high was not found."

def test_get_golden_pocket():
    df = create_synthetic_data()
    
    # Confirm it after index 19
    as_of_date = df.index[25]
    
    pocket = get_golden_pocket(df, as_of_date=as_of_date, min_swing_pct=8.0, order=5)
    
    assert pocket is not None
    assert pocket['swing_start'] == df.index[4]
    assert pocket['swing_end'] == df.index[14]
    
    # Start price (Low at index 4) = 98.0
    # End price (High at index 14) = 152.0
    # Swing diff = 152 - 98 = 54
    # 50% = 152 - 0.5 * 54 = 125.0
    # 61.8% = 152 - 0.618 * 54 = 118.628
    
    assert np.isclose(pocket['fib_50'], 125.0)
    assert np.isclose(pocket['fib_618'], 118.628)
    assert np.isclose(pocket['pocket_low'], 118.628)
    assert np.isclose(pocket['pocket_high'], 125.0)

