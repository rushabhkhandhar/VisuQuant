def compute_signal_score(config, features, direction):
    """
    Computes a point-based score based on configurable thresholds.
    direction: "LONG" or "SHORT"
    """
    score = 0
    reasons = []
    
    # 1. Gap Calculation
    gap_pct = features['gap_pct']
    if direction == "LONG":
        if gap_pct >= config['min_gap_pct']:
            score += 1
            reasons.append(f"Gap +1 (Gap {gap_pct:.2f}%)")
    else:
        if gap_pct <= -config['min_gap_pct']:
            score += 1
            reasons.append(f"Gap +1 (Gap {gap_pct:.2f}%)")
            
    # 2. RVOL Calculation
    rvol = features['rvol']
    if rvol >= config['rvol_threshold_2']:
        score += 3
        reasons.append(f"RVOL +3 (RVOL {rvol:.2f}x)")
    elif rvol >= config['rvol_threshold_1']:
        score += 2
        reasons.append(f"RVOL +2 (RVOL {rvol:.2f}x)")
        
    # 3. VWAP
    price = features['current_price']
    vwap = features['vwap']
    vwap_slope = features['vwap_slope']
    
    if direction == "LONG":
        if price > vwap:
            score += 2
            reasons.append(f"VWAP +2 (Price > VWAP)")
        if vwap_slope > 0:
            score += 1
            reasons.append(f"VWAP Slope +1 (Rising VWAP)")
    else:
        if price < vwap:
            score += 2
            reasons.append(f"VWAP +2 (Price < VWAP)")
        if vwap_slope < 0:
            score += 1
            reasons.append(f"VWAP Slope +1 (Falling VWAP)")
            
    # 4. ORB Width Filter
    or_width_pct = features['or_width_pct']
    if or_width_pct <= config['max_or_width_pct']:
        score += 1
        reasons.append(f"OR Coil +1 (OR Width {or_width_pct:.2f}%)")
        
    # 5. ORB Breakout (Mandatory to be considered a setup, but adds points here)
    orh = features['orh']
    orl = features['orl']
    if direction == "LONG" and price > orh:
        score += 3
        reasons.append(f"ORH Break +3 (Price {price} > {orh})")
    elif direction == "SHORT" and price < orl:
        score += 3
        reasons.append(f"ORL Break +3 (Price {price} < {orl})")
        
    # 6. Breakout Volume Confirmation
    bo_vol_ratio = features['breakout_vol_ratio']
    if bo_vol_ratio >= 1.5:
        score += 2
        reasons.append(f"BO Vol +2 ({bo_vol_ratio:.1f}x)")
        
    # 7. NIFTY Alignment
    nifty_vwap = features['nifty_vwap']
    nifty_price = features['nifty_price']
    if direction == "LONG" and nifty_price > nifty_vwap:
        score += 2
        reasons.append(f"NIFTY +2 (NIFTY > VWAP)")
    elif direction == "SHORT" and nifty_price < nifty_vwap:
        score += 2
        reasons.append(f"NIFTY +2 (NIFTY < VWAP)")
        
    # 8. Sector Alignment
    if features.get('sector_vwap') is not None:
        sec_price = features['sector_price']
        sec_vwap = features['sector_vwap']
        if direction == "LONG" and sec_price > sec_vwap:
            score += 2
            reasons.append(f"Sector +2 (Sector > VWAP)")
        elif direction == "SHORT" and sec_price < sec_vwap:
            score += 2
            reasons.append(f"Sector +2 (Sector < VWAP)")
            
    # 9. Relative Strength
    rs = features['relative_strength']
    if direction == "LONG" and rs > 0:
        score += 2
        reasons.append(f"RS +2 (RS {rs:.2f}%)")
    elif direction == "SHORT" and rs < 0:
        score += 2
        reasons.append(f"RS +2 (RS {rs:.2f}%)")
        
    # 10. Good R:R
    rr = features['rr']
    if rr >= config['min_rr']:
        score += 2
        reasons.append(f"R:R +2 (R:R {rr:.2f})")
        
    return score, reasons
