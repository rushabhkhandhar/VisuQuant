import pandas as pd
from typing import Dict, List
from src.screener.screens.connors_rsi import compute_connors_rsi

def connors_rsi_fade(df: pd.DataFrame, threshold: float = 90.0, disabled_triggers: List[str] = None) -> Dict:
    """
    ConnorsRSI Fade Trigger for Short Pipeline.
    Fires when ConnorsRSI > 90 (extremely overbought short-term bounce in a downtrend).
    """
    if disabled_triggers and "connors_rsi_fade" in disabled_triggers:
        return {"passed": False, "reason": "Disabled by regime"}
        
    if df.empty or len(df) < 100:
        return {"passed": False}

    crsi_series = compute_connors_rsi(df)
    
    if crsi_series is None or crsi_series.empty:
        return {"passed": False}
        
    current_crsi = crsi_series.iloc[-1]
    
    if pd.isna(current_crsi):
        return {"passed": False}
        
    passed = bool(current_crsi >= threshold)
    
    return {
        "passed": passed,
        "crsi_value": float(current_crsi)
    }
