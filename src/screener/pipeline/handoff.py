import sys
import os
import json
import argparse
from datetime import date

# Ensure src module is accessible
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.screener.pipeline.run_daily_screen import run_screener

def get_validation_note(trigger_type: str) -> str:
    """
    Returns the validated backtest performance for a given trigger to be passed
    downstream for the final PDF report.
    """
    if "Bullish Engulfing" in trigger_type:
        return "Bullish Engulfing: 55-60% 20d hit rate, +1.5% to +2.6% avg excess return. Durable edge across 18-month walk-forward blocks."
    elif "Bollinger Breakout" in trigger_type:
        return "Bollinger Breakout: Fragile edge. Highly regime-dependent (+4.0% in uptrends, -9.0% in downtrends). Strict adherence to trend confluence required."
    elif "Morning Star" in trigger_type:
        return "Morning Star: Reversal pattern structurally similar to Engulfing. Currently in Watchlist mode pending larger sample size."
    else:
        return f"{trigger_type}: Standard moving average bounce / technical setup."

def generate_handoff_payloads(candidates: list, current_regime: str) -> list:
    """
    Packages the final screener candidates into the strict schema expected
    by the VisuQuant charting and Vision AI pipeline.
    """
    payloads = []
    
    for cand in candidates:
        symbol = cand["symbol"]
        trigger_type = cand["trigger_type"]
        score = cand["score"]
        metrics = cand.get("metrics", {})
        
        payload = {
            "ticker": symbol,
            "screener_context": {
                "trigger_type": trigger_type,
                "composite_score": score,
                "metrics": {
                    "atr_ratio": metrics.get("atr_ratio"),
                    "pct_from_high": metrics.get("pct_from_high"),
                    "in_golden_pocket": metrics.get("fibonacci", {}).get("in_golden_pocket", False)
                },
                "market_regime": current_regime,
                "validation_note": get_validation_note(trigger_type)
            }
        }
        payloads.append(payload)
        
    return payloads

def get_handoff_payloads(as_of_date: date = None) -> list:
    if as_of_date is None:
        as_of_date = date.today()
        
    print(f"\n--- VISUQUANT AUTOMATED SCREENER ---")
    print(f"Date: {as_of_date}\n")
    
    # 1. Run the core screener (which automatically checks regime, liquidity, Stage 1 & 2)
    results = run_screener(as_of_date=as_of_date, dry_run=False, top_n=5, check_regime=True)
    
    candidates = results.get("candidates", [])
    regime = results.get("regime", "UNKNOWN")
    
    if not candidates:
        print("\nNo candidates survived the screener today.")
        return []
        
    # 2. Format payloads for Chart Capture
    payloads = generate_handoff_payloads(candidates, regime)
    return payloads
