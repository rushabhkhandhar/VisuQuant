import pytest
import pandas as pd
from datetime import date, timedelta
from unittest.mock import patch
from src.data.nse_fetcher import get_ohlcv

def test_get_ohlcv_with_synthetic_data():
    # Create synthetic daily data
    dates = pd.date_range(start="2026-01-01", periods=5, freq="B")
    
    # Day 1: Normal
    # Day 2: Normal
    # Day 3: Circuit Day (High == Low)
    # Day 4: Corporate Action Gap (> 20% drop from previous close)
    # Day 5: Normal
    
    synthetic_data = pd.DataFrame({
        "Open":   [100.0, 102.0, 105.0, 50.0,  52.0],
        "High":   [105.0, 106.0, 105.0, 55.0,  54.0],
        "Low":    [98.0,  101.0, 105.0, 48.0,  50.0],
        "Close":  [103.0, 104.0, 105.0, 53.0,  51.0],
        "Volume": [1000,  1200,  500,   5000,  1500]
    }, index=dates)
    synthetic_data.index.name = "Date"
    
    with patch('src.data.nse_fetcher.fetch_daily_candles', return_value=synthetic_data):
        df = get_ohlcv("TESTSYM", date(2026, 1, 1), date(2026, 1, 7))
        
        assert df is not None
        assert len(df) == 5
        
        # Test Circuit Day (Day 3, index 2)
        assert df.iloc[2]["is_circuit_day"] == True
        assert df.iloc[0]["is_circuit_day"] == False
        
        # Test Corporate Action Gap (Day 4, index 3)
        assert df.iloc[3]["is_corporate_action_gap"] == True
        assert df.iloc[1]["is_corporate_action_gap"] == False
        
        # Test Columns
        expected_cols = ["Open", "High", "Low", "Close", "Volume", "is_circuit_day", "is_corporate_action_gap"]
        for col in expected_cols:
            assert col in df.columns
