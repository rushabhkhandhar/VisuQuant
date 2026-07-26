def validate_trade_parameters(tech_ind: dict, confluence: dict, risk: dict, decision_node: dict) -> dict:
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
        "confluence": False
    }

    decision = decision_node.get("decision", {}) if decision_node else {}
    
    # 1. Decision Validation
    rec = decision.get("recommendation", "")
    valid_recs = ["STRONG BUY", "BUY", "HOLD", "SELL", "STRONG SELL", "AVOID"]
    if rec in valid_recs:
        checks["decision"] = True
    else:
        errors.append(f"Invalid recommendation: '{rec}'. Must be one of {valid_recs}.")

    # 2. Confidence Validation
    conf = decision.get("confidence")
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
        if pos_size in ["Small", "Medium", "Large"]:
            checks["position_size"] = True
        else:
            errors.append(f"Invalid position size: '{pos_size}'. Must be Small, Medium, or Large.")

        risk_level = risk.get("risk_level")
        if risk_level in ["Low", "Moderate", "High"]:
            checks["risk"] = True
        else:
            errors.append(f"Invalid risk level: '{risk_level}'. Must be Low, Moderate, or High.")

        volatility = risk.get("volatility")
        if volatility in ["Low", "Medium", "High"]:
            checks["volatility"] = True
        else:
            errors.append(f"Invalid volatility: '{volatility}'. Must be Low, Medium, or High.")
    else:
        errors.append("Risk analysis block is missing.")
        
    # 3, 4, 5. Execution & Targets Validation
    execution = decision.get("execution", {})
    if rec == "HOLD":
        if execution.get("entry") is not None or execution.get("stop_loss") is not None or execution.get("targets"):
            warnings.append("HOLD recommendation contains active execution plan.")
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
            "failed_check_names": failed_check_names
        },
        "errors": errors,
        "warnings": warnings,
        "checks": checks
    }
