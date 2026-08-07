import pytest
import pandas as pd
from datetime import date

# Since run_backtest is a monolithic function, we can just extract the logic we need to test,
# or mock it out. We will write a test that constructs a dataframe with a signal very near the end
# and verifies our logic correctly drops it.

def simulate_forward_return_logic(signals, df):
    results = []
    for sig in signals:
        t_date = sig["date"]
        try:
            t_idx = df.index.get_loc(t_date)
        except KeyError:
            continue
            
        if t_idx + 1 + 20 >= len(df):
            continue 
            
        entry_price = df['Open'].iloc[t_idx + 1]
        
        ret_5d = (df['Close'].iloc[t_idx + 1 + 5] - entry_price) / entry_price
        ret_10d = (df['Close'].iloc[t_idx + 1 + 10] - entry_price) / entry_price
        ret_20d = (df['Close'].iloc[t_idx + 1 + 20] - entry_price) / entry_price
        
        results.append({
            "trigger": sig["trigger_type"],
            "ret_5d": ret_5d,
            "ret_10d": ret_10d,
            "ret_20d": ret_20d
        })
    return results

def test_signal_without_full_forward_window_is_excluded():
    # Construct a dataframe of 100 days
    dates = pd.date_range(start="2026-01-01", periods=100, freq="B")
    df = pd.DataFrame({
        "Open": [100.0] * 100,
        "High": [100.0] * 100,
        "Low": [100.0] * 100,
        "Close": [100.0] * 100,
        "Volume": [1000] * 100
    }, index=dates)
    
    # 1. Valid Signal: At index 50, has 49 days of forward data (which is > 21)
    sig_valid = {"date": dates[50], "symbol": "TEST", "trigger_type": "Breakout"}
    
    # 2. Invalid Signal: At index 85, has 14 days of forward data (which is < 21)
    sig_invalid = {"date": dates[85], "symbol": "TEST", "trigger_type": "Breakout"}
    
    signals = [sig_valid, sig_invalid]
    
    results = simulate_forward_return_logic(signals, df)
    
    # We should only get ONE result back
    assert len(results) == 1
    assert results[0]["ret_5d"] == 0.0
    assert results[0]["ret_10d"] == 0.0
    assert results[0]["ret_20d"] == 0.0
