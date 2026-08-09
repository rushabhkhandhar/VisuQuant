import pandas as pd
from typing import Dict, List

def donchian_breakdown(df: pd.DataFrame, period: int = 20, volume_mult: float = 1.5, disabled_triggers: List[str] = None) -> Dict:
    """
    Donchian Channel Breakdown Trigger (Turtle Short)
    Fires when the stock closes below the lowest low of the last N periods.
    """
    if disabled_triggers and "donchian_breakdown" in disabled_triggers:
        return {"passed": False, "reason": "Disabled by regime"}
        
    if df.empty or len(df) < period + 1:
        return {"passed": False}

    current_close = df['Close'].iloc[-1]
    current_volume = df['Volume'].iloc[-1]
    
    # Lowest low over the past N days (excluding today)
    lowest_low_N = df['Low'].iloc[-period-1:-1].min()
    
    # Average volume over the past N days (excluding today)
    avg_volume_N = df['Volume'].iloc[-period-1:-1].mean()
    
    passed = False
    
    # Breakdown logic
    if current_close < lowest_low_N:
        if current_volume >= (avg_volume_N * volume_mult):
            passed = True
            
    return {
        "passed": passed,
        "lowest_low": float(lowest_low_N),
        "trigger_price": float(current_close),
        "volume_surge": float(current_volume / avg_volume_N) if avg_volume_N > 0 else 0
    }
