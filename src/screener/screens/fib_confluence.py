import pandas as pd
from src.screener.indicators.core import find_swing_points

def get_golden_pocket(df: pd.DataFrame, as_of_date: pd.Timestamp, min_swing_pct: float = 8.0, order: int = 5) -> dict:
    """
    1. Call find_swing_points up to as_of_date
    2. Identify the most recent significant swing (low-to-high or high-to-low) 
       with magnitude >= min_swing_pct
    3. Compute the 0.5 and 0.618 retracement levels
    4. Return golden pocket dict, or None if no qualifying swing exists
    """
    swings = find_swing_points(df, as_of_date=as_of_date, order=order)
    
    if not swings or len(swings) < 2:
        return None
        
    for i in range(len(swings) - 1, 0, -1):
        end_swing = swings[i]
        
        # Find the most recent opposite swing before it
        start_swing = None
        for j in range(i - 1, -1, -1):
            if swings[j][2] != end_swing[2]:
                start_swing = swings[j]
                break
                
        if start_swing is None:
            continue
            
        start_date, start_price, start_type = start_swing
        end_date, end_price, end_type = end_swing
        
        # Magnitude relative to start price
        magnitude_pct = (abs(end_price - start_price) / start_price) * 100.0
        
        if magnitude_pct >= min_swing_pct:
            swing_diff = end_price - start_price
            fib_50 = end_price - 0.5 * swing_diff
            fib_618 = end_price - 0.618 * swing_diff
            
            return {
                "swing_start": start_date,
                "swing_end": end_date,
                "fib_50": fib_50,
                "fib_618": fib_618,
                "pocket_low": min(fib_50, fib_618),
                "pocket_high": max(fib_50, fib_618)
            }
            
    return None
