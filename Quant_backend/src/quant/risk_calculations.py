from src.screener import config

def calculate_risk_parameters(tech_ind: dict, confluence: dict, scraped: dict, unified_trend: dict = None) -> dict:
    warnings = []
    
    # 1. Base Price (Entry)
    entry = None
    if scraped and "current_price" in scraped:
        entry = float(scraped["current_price"])
    elif scraped and "entry_price" in scraped:
        entry = float(scraped["entry_price"])
    elif tech_ind.get("pivot_points") and tech_ind["pivot_points"].get("P"):
        entry = float(tech_ind["pivot_points"]["P"])
        
    if not entry:
        warnings.append("No reliable entry price found. Risk metrics cannot be accurately calculated.")
        return {
            "entry": None, "stop_loss": None, "targets": {"target_1": None, "target_2": None, "target_3": None},
            "risk_reward": {"target_1": None, "target_2": None, "target_3": None}, "position_size": "Unknown",
            "trade_confidence": 0, "risk_level": "Unknown", "volatility": "Unknown", "warnings": warnings
        }
        
    # 2. Trade Confidence
    confidence = 0
    if confluence and "overall_confluence" in confluence:
        confidence = confluence["overall_confluence"].get("score", 0)
        
    # 3. Volatility Assessment
    atr = tech_ind.get("atr")
    volatility = "Medium"
    if atr:
        atr_pct = (atr / entry) * 100
        if atr_pct < config.VOLATILITY_LOW_ATR_PCT:
            volatility = "Low"
        elif atr_pct > config.VOLATILITY_HIGH_ATR_PCT:
            volatility = "High"
    else:
        warnings.append("ATR unavailable. Volatility assessment is falling back to Bollinger Bands.")
        bb = tech_ind.get("bollinger_bands", {})
        upper = bb.get("upper")
        lower = bb.get("lower")
        middle = bb.get("middle")
        if upper and lower and middle:
            bb_width = (upper - lower) / middle * 100
            if bb_width < 2.0:
                volatility = "Low"
            elif bb_width > 6.0:
                volatility = "High"

    # Determine Direction
    direction = "Bullish"
    if unified_trend and unified_trend.get("direction"):
        if "Bearish" in unified_trend["direction"]:
            direction = "Bearish"
            
    # 4. Stop Loss
    stop_loss = None
    if direction == "Bullish":
        if atr:
            stop_loss = round(entry - (config.CHANDELIER_ATR_MULT * atr), 2)
        elif tech_ind.get("swing_low"):
            stop_loss = round(tech_ind["swing_low"], 2)
        elif tech_ind.get("pivot_points") and tech_ind["pivot_points"].get("S1"):
            stop_loss = round(tech_ind["pivot_points"]["S1"], 2)
            
        if not stop_loss or stop_loss >= entry:
            stop_loss = round(entry * (1 - config.FALLBACK_SL_PCT), 2)
            warnings.append("Using fallback stop loss due to lack of support indicators.")
    else: # Bearish
        if atr:
            stop_loss = round(entry + (config.CHANDELIER_ATR_MULT * atr), 2)
        elif tech_ind.get("swing_high"):
            stop_loss = round(tech_ind["swing_high"], 2)
        elif tech_ind.get("pivot_points") and tech_ind["pivot_points"].get("R1"):
            stop_loss = round(tech_ind["pivot_points"]["R1"], 2)
            
        if not stop_loss or stop_loss <= entry:
            stop_loss = round(entry * (1 + config.FALLBACK_SL_PCT), 2)
            warnings.append("Using fallback stop loss due to lack of resistance indicators.")
        
    risk_amount = abs(entry - stop_loss)
    
    # 5. Targets
    t1, t2, t3 = None, None, None
    if direction == "Bullish":
        if atr:
            t1 = round(entry + (config.CHANDELIER_ATR_MULT * atr), 2)
            t2 = round(entry + (config.CHANDELIER_ATR_MULT * 2 * atr), 2)
            t3 = round(entry + (config.CHANDELIER_ATR_MULT * 3.33 * atr), 2)
        elif tech_ind.get("pivot_points"):
            pp = tech_ind["pivot_points"]
            t1 = pp.get("R1", round(entry * 1.02, 2))
            t2 = pp.get("R2", round(entry * 1.04, 2))
            t3 = round(entry * 1.06, 2)
        else:
            t1 = round(entry * 1.02, 2)
            t2 = round(entry * 1.04, 2)
            t3 = round(entry * 1.06, 2)
            warnings.append("Using fixed percentage targets due to lack of volatility/pivot indicators.")
    else: # Bearish
        if atr:
            t1 = round(entry - (config.CHANDELIER_ATR_MULT * atr), 2)
            t2 = round(entry - (config.CHANDELIER_ATR_MULT * 2 * atr), 2)
            t3 = round(entry - (config.CHANDELIER_ATR_MULT * 3.33 * atr), 2)
        elif tech_ind.get("pivot_points"):
            pp = tech_ind["pivot_points"]
            t1 = pp.get("S1", round(entry * 0.98, 2))
            t2 = pp.get("S2", round(entry * 0.96, 2))
            t3 = round(entry * 0.94, 2)
        else:
            t1 = round(entry * 0.98, 2)
            t2 = round(entry * 0.96, 2)
            t3 = round(entry * 0.94, 2)
            warnings.append("Using fixed percentage targets due to lack of volatility/pivot indicators.")

    # 6. Risk / Reward Ratios
    def calc_rr(target, entry_price, risk, trade_dir):
        if not target or not entry_price or risk <= 0:
            return None
        if trade_dir == "Bullish":
            return round((target - entry_price) / risk, 2)
        else:
            return round((entry_price - target) / risk, 2)

    rr1 = calc_rr(t1, entry, risk_amount, direction)
    rr2 = calc_rr(t2, entry, risk_amount, direction)
    rr3 = calc_rr(t3, entry, risk_amount, direction)
    
    # 7. Position Sizing
    position_size = "Medium"
    if volatility == "High" or confidence < 50:
        position_size = "Small"
    elif volatility == "Low" and confidence > 75:
        position_size = "Large"
        
    # 8. Risk Level
    risk_level = "Moderate"
    if volatility == "High":
        risk_level = "High"
    elif volatility == "Low" and confidence > 70:
        risk_level = "Low"
        
    # 9. Minimum Risk Reward Validation
    valid_rrs = [rr for rr in [rr1, rr2, rr3] if rr is not None]
    best_rr = max(valid_rrs) if valid_rrs else 0
    meets_rr = bool(best_rr >= 1.5)
        
    return {
        "entry": entry,
        "stop_loss": stop_loss,
        "targets": {
            "target_1": t1,
            "target_2": t2,
            "target_3": t3
        },
        "risk_reward": {
            "target_1": rr1,
            "target_2": rr2,
            "target_3": rr3
        },
        "metrics": {
            "best_risk_reward": best_rr,
            "meets_min_rr_threshold": meets_rr
        },
        "position_size": position_size,
        "trade_confidence": confidence,
        "risk_level": risk_level,
        "volatility": volatility,
        "warnings": warnings
    }
