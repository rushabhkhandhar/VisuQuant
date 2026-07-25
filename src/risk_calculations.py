def calculate_risk_parameters(tech_ind: dict, confluence: dict, scraped: dict) -> dict:
    warnings = []
    
    # 1. Base Price (Entry)
    entry = None
    if scraped and "last_price" in scraped:
        entry = float(scraped["last_price"])
    elif tech_ind.get("vwap"):
        entry = float(tech_ind["vwap"])
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
        if atr_pct < 1.0:
            volatility = "Low"
        elif atr_pct > 3.0:
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

    # 4. Stop Loss (Baseline Long Scenario)
    stop_loss = None
    if atr:
        stop_loss = round(entry - (1.5 * atr), 2)
    elif tech_ind.get("swing_low"):
        stop_loss = round(tech_ind["swing_low"], 2)
    elif tech_ind.get("pivot_points") and tech_ind["pivot_points"].get("S1"):
        stop_loss = round(tech_ind["pivot_points"]["S1"], 2)
        
    if not stop_loss or stop_loss >= entry:
        stop_loss = round(entry * 0.95, 2) # 5% fallback
        warnings.append("Using 5% fallback stop loss due to lack of support indicators.")
        
    risk_amount = entry - stop_loss
    
    # 5. Targets (Baseline Long Scenario)
    t1, t2, t3 = None, None, None
    if atr:
        t1 = round(entry + (1.5 * atr), 2)
        t2 = round(entry + (3.0 * atr), 2)
        t3 = round(entry + (5.0 * atr), 2)
    elif tech_ind.get("pivot_points"):
        pp = tech_ind["pivot_points"]
        t1 = pp.get("R1", round(entry * 1.02, 2))
        t2 = pp.get("R2", round(entry * 1.04, 2))
        t3 = round(entry * 1.06, 2) # fallback
    else:
        t1 = round(entry * 1.02, 2)
        t2 = round(entry * 1.04, 2)
        t3 = round(entry * 1.06, 2)
        warnings.append("Using fixed percentage targets due to lack of volatility/pivot indicators.")

    # 6. Risk / Reward Ratios
    def calc_rr(target, entry_price, risk):
        if not target or not entry_price or risk <= 0:
            return None
        return round((target - entry_price) / risk, 2)

    rr1 = calc_rr(t1, entry, risk_amount)
    rr2 = calc_rr(t2, entry, risk_amount)
    rr3 = calc_rr(t3, entry, risk_amount)
    
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
        "position_size": position_size,
        "trade_confidence": confidence,
        "risk_level": risk_level,
        "volatility": volatility,
        "warnings": warnings
    }
