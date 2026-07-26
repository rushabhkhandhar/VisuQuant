def validate_trade_parameters(tech_ind: dict, confluence: dict, risk: dict, decision_node: dict, unified_trend: dict = None) -> dict:
    errors = []
    warnings = []
    checks = {
        "decision": False,
        "confidence": False,
        "execution": False,
        "risk": False,
        "targets": False,
        "position_size": False,
        "volatility": False,
        "confluence": False,
        "consistency": True
    }

    decision = decision_node.get("decision", {}) if decision_node else {}
    
    # 0. Consistency Validator
    if unified_trend:
        trend_dir = unified_trend.get("direction", "Unknown")
        ms_trend = tech_ind.get("market_structure", {}).get("trend", "Unknown")
        
        if trend_dir in ["Bullish", "Bearish"] and ms_trend in ["Bullish", "Bearish"] and trend_dir != ms_trend:
            warnings.append({
                "severity": "Medium",
                "module": "Consistency Engine",
                "reason": f"Market Structure ({ms_trend}) contradicts Unified Trend ({trend_dir}).",
                "resolution": "Downgrading confidence by 0.2."
            })
            if "confidence" in decision:
                decision["confidence"] = max(0.0, decision["confidence"] - 0.2)
                checks["consistency"] = False
                
        rec = decision.get("recommendation", "")
        if rec in ["STRONG BUY", "BUY"] and trend_dir == "Bearish":
            warnings.append({
                "severity": "High",
                "module": "Decision Engine",
                "reason": "BUY recommendation conflicts with Bearish trend.",
                "resolution": "Downgrading confidence by 0.2."
            })
            if "confidence" in decision:
                decision["confidence"] = max(0.0, decision["confidence"] - 0.2)
                checks["consistency"] = False
        elif rec in ["STRONG SELL", "SELL"] and trend_dir == "Bullish":
            warnings.append({
                "severity": "High",
                "module": "Decision Engine",
                "reason": "SELL recommendation conflicts with Bullish trend.",
                "resolution": "Downgrading confidence by 0.2."
            })
            if "confidence" in decision:
                decision["confidence"] = max(0.0, decision["confidence"] - 0.2)
                checks["consistency"] = False

    # Check: Unknown Volume despite clear trend
    vol = tech_ind.get("interpretations", {}).get("Volume", {}).get("Interpretation", "")
    if "Unknown" in vol or vol == "":
        warnings.append({
            "severity": "Low",
            "module": "Confluence Engine",
            "reason": "Volume interpretation is missing or Unknown.",
            "resolution": "Check volume data availability."
        })

    # Check: High confidence but unknown trend
    conf = decision.get("confidence")
    if conf is not None and conf > 0.7:
        if unified_trend and unified_trend.get("direction") == "Unknown":
            warnings.append({
                "severity": "High",
                "module": "Decision Engine",
                "reason": "High confidence recommendation despite Unknown trend.",
                "resolution": "Review trade justification."
            })
            checks["consistency"] = False
            
    # Check: Bullish EMA but Bearish summary or vice-versa
    ema_trend = ""
    for k, v in tech_ind.get("interpretations", {}).items():
        if "EMA" in k:
            ema_trend = v.get("Impact", "")
            break
            
    if rec in ["STRONG BUY", "BUY"] and ema_trend == "Bearish":
        warnings.append({
            "severity": "Medium",
            "module": "Consistency Engine",
            "reason": "BUY recommendation conflicts with Bearish EMA alignment.",
            "resolution": "Downgrading confidence by 0.1."
        })
        if "confidence" in decision:
            decision["confidence"] = max(0.0, decision["confidence"] - 0.1)
    elif rec in ["STRONG SELL", "SELL"] and ema_trend == "Bullish":
        warnings.append({
            "severity": "Medium",
            "module": "Consistency Engine",
            "reason": "SELL recommendation conflicts with Bullish EMA alignment.",
            "resolution": "Downgrading confidence by 0.1."
        })
        if "confidence" in decision:
            decision["confidence"] = max(0.0, decision["confidence"] - 0.1)

    # 1. Decision Validation
    valid_recs = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL", "AVOID"]
    if rec in valid_recs:
        checks["decision"] = True
    else:
        errors.append(f"Invalid recommendation: '{rec}'. Must be one of {valid_recs}.")

    # 2. Confidence Validation
    if conf is not None and isinstance(conf, (int, float)) and 0 <= conf <= 100:
        checks["confidence"] = True
    else:
        errors.append(f"Invalid confidence: {conf}. Must be between 0 and 100.")

    # 9. Confluence Validation
    overall_conf = confluence.get("overall_confluence", {}) if confluence else {}
    conf_score = overall_conf.get("score")
    if conf_score is not None and isinstance(conf_score, (int, float)) and 0 <= conf_score <= 100:
        checks["confluence"] = True
    else:
        errors.append("Invalid or missing confluence score. Must be between 0 and 100.")

    # 6, 7, 8. Risk and Volatility Validation
    if risk:
        pos_size = risk.get("position_size")
        if pos_size in ["Small", "Medium", "Large", "Unknown"]:
            checks["position_size"] = True
        else:
            errors.append(f"Invalid position size: '{pos_size}'. Must be Small, Medium, Large, or Unknown.")

        risk_level = risk.get("risk_level")
        if risk_level in ["Low", "Moderate", "High", "Unknown"]:
            checks["risk"] = True
        else:
            errors.append(f"Invalid risk level: '{risk_level}'. Must be Low, Moderate, High, or Unknown.")

        volatility = risk.get("volatility")
        if volatility in ["Low", "Medium", "High", "Unknown"]:
            checks["volatility"] = True
        else:
            errors.append(f"Invalid volatility: '{volatility}'. Must be Low, Medium, High, or Unknown.")
    else:
        errors.append("Risk analysis block is missing.")
        
    # 3, 4, 5. Execution & Targets Validation
    execution = decision.get("execution", {})
    if rec == "HOLD":
        if execution.get("entry") is not None or execution.get("stop_loss") is not None or execution.get("targets"):
            warnings.append({
                "severity": "Medium",
                "module": "Decision Engine",
                "reason": "HOLD recommendation contains active execution plan.",
                "resolution": "Ignore execution plan."
            })
        checks["execution"] = True
        checks["targets"] = True
    elif rec in ["BUY", "STRONG BUY", "SELL", "STRONG SELL"]:
        entry = execution.get("entry")
        sl = execution.get("stop_loss")
        targets = execution.get("targets", {})
        t1, t2, t3 = targets.get("target_1"), targets.get("target_2"), targets.get("target_3")
        
        if entry is None or sl is None or not targets:
            errors.append("Execution plan is missing entry, stop_loss, or targets.")
        else:
            checks["execution"] = True
            
            try:
                entry = float(entry)
                sl = float(sl)
                t1 = float(t1) if t1 is not None else None
                t2 = float(t2) if t2 is not None else None
                t3 = float(t3) if t3 is not None else None
                
                targets_valid = True
                if rec in ["BUY", "STRONG BUY"]:
                    if sl >= entry:
                        errors.append("BUY recommendation has Stop Loss above or equal to Entry.")
                        targets_valid = False
                    if t1 and t1 <= entry:
                        errors.append("Target 1 is below Entry.")
                        targets_valid = False
                    if t1 and t2 and t2 <= t1:
                        errors.append("Target 2 is below Target 1.")
                        targets_valid = False
                    if t2 and t3 and t3 <= t2:
                        errors.append("Target 3 is below Target 2.")
                        targets_valid = False
                elif rec in ["SELL", "STRONG SELL"]:
                    if sl <= entry:
                        errors.append("SELL recommendation has Stop Loss below or equal to Entry.")
                        targets_valid = False
                    if t1 and t1 >= entry:
                        errors.append("Target 1 is above Entry.")
                        targets_valid = False
                    if t1 and t2 and t2 >= t1:
                        errors.append("Target 2 is above Target 1.")
                        targets_valid = False
                    if t2 and t3 and t3 >= t2:
                        errors.append("Target 3 is above Target 2.")
                        targets_valid = False
                        
                risk_reward = risk.get("risk_reward", {}) if risk else {}
                rr1 = risk_reward.get("target_1")
                if rr1 is None or rr1 <= 0:
                    errors.append("Risk Reward must be strictly positive.")
                    targets_valid = False
                    
                if targets_valid:
                    checks["targets"] = True
                    
            except (ValueError, TypeError):
                errors.append("Execution values must be numeric.")

    is_valid = len(errors) == 0

    passed_check_names = [k for k, v in checks.items() if v]
    failed_check_names = [k for k, v in checks.items() if not v]

    return {
        "valid": is_valid,
        "summary": {
            "passed_checks": len(passed_check_names),
            "failed_checks": len(failed_check_names),
            "warnings": len(warnings),
            "errors": len(errors),
            "passed_check_names": passed_check_names,
            "failed_check_names": failed_check_names,
            "detailed_warnings": warnings
        },
        "errors": errors,
        "warnings": warnings,
        "checks": checks
    }
