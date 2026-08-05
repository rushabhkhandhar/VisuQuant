import pandas as pd
from src.screener.indicators.core import find_swing_points

def score_fib_confluence(df: pd.DataFrame, min_swing_magnitude_pct: float = 0.05, margin_pct: float = 0.005) -> dict:
    """
    Enriches a candidate's metrics with a Fibonacci golden pocket confluence score.
    Identifies the most recent significant swing and checks if the subsequent pullback 
    bottomed (or topped) inside the 0.5 - 0.618 retracement zone.
    """
    swings = find_swing_points(df, order=5)
    highs = swings['highs']
    lows = swings['lows']
    
    default_result = {
        "in_golden_pocket": False,
        "fib_0_50": None,
        "fib_0_618": None,
        "swing_p1_type": None,
        "swing_p1_price": None,
        "swing_p2_price": None,
        "pullback_extreme": None
    }
    
    if not highs or not lows:
        return default_result
        
    # Combine and sort all swings chronologically
    all_swings = [("high", date, price) for date, price in highs] + \
                 [("low", date, price) for date, price in lows]
    all_swings.sort(key=lambda x: x[1])
    
    # Find the most recent valid pair of alternating swings with sufficient magnitude
    recent_swing = None
    p2_date = None
    
    for i in range(len(all_swings) - 1, 0, -1):
        p2_type, p2_d, p2_price = all_swings[i]
        p1_type, p1_d, p1_price = all_swings[i-1]
        
        if p1_type != p2_type:
            mag = abs(p2_price - p1_price) / min(p2_price, p1_price)
            if mag >= min_swing_magnitude_pct:
                recent_swing = (p1_type, p1_price, p2_type, p2_price)
                p2_date = p2_d
                break
                
    if not recent_swing:
        return default_result
        
    p1_type, p1_price, p2_type, p2_price = recent_swing
    diff = abs(p2_price - p1_price)
    
    if p1_type == "low" and p2_type == "high":
        # Uptrend swing: Low -> High. Retracement goes down from High.
        fib_050 = p2_price - 0.5 * diff
        fib_618 = p2_price - 0.618 * diff
    else:
        # Downtrend swing: High -> Low. Retracement goes up from Low.
        fib_050 = p2_price + 0.5 * diff
        fib_618 = p2_price + 0.618 * diff
        
    upper_bound = max(fib_050, fib_618)
    lower_bound = min(fib_050, fib_618)
    
    # Determine the extreme point of the pullback since the peak/trough (p2)
    recent_bars = df[df.index >= p2_date]
    if recent_bars.empty:
        return default_result
        
    if p1_type == "low" and p2_type == "high":
        # For an uptrend swing, the pullback is a dip, so we look for the lowest point
        pullback_extreme = recent_bars['Low'].min()
    else:
        # For a downtrend swing, the pullback is a rally, so we look for the highest point
        pullback_extreme = recent_bars['High'].max()
        
    # Check if the pullback extreme sits within the golden pocket (allowing a small margin of error)
    margin = pullback_extreme * margin_pct
    in_pocket = (pullback_extreme >= (lower_bound - margin)) and (pullback_extreme <= (upper_bound + margin))
    
    return {
        "in_golden_pocket": bool(in_pocket),
        "fib_0_50": float(fib_050),
        "fib_0_618": float(fib_618),
        "swing_p1_type": p1_type,
        "swing_p1_price": float(p1_price),
        "swing_p2_price": float(p2_price),
        "pullback_extreme": float(pullback_extreme)
    }
