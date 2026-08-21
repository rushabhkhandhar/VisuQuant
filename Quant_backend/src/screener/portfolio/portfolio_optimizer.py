import os
import sys
import pandas as pd
import numpy as np
import logging
import warnings
from datetime import datetime, date

from pypfopt import risk_models, expected_returns
from pypfopt.black_litterman import BlackLittermanModel
from pypfopt.efficient_frontier import EfficientFrontier

# Ignore PyPortfolioOpt warnings for clean output
warnings.filterwarnings("ignore", module="pypfopt")

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
from src.data.nse_fetcher import fetch_bulk_history

logger = logging.getLogger(__name__)

# --- CONFIGURATION / CONSTANTS ---
CAPITAL = 1_00_000.0
MAX_WEIGHT = 0.20
MIN_POSITION_WEIGHT = 0.01
MAX_RISK_PER_TRADE_PCT = 0.01  # Max 1% portfolio risk per trade

PORTFOLIO_LOOKBACK_DAYS = 504  # ~2 years
MIN_HISTORY_DAYS = 200

COVARIANCE_METHOD = "ledoit_wolf"

# Neutral BL assumptions (Annualized expected returns for PyPortfolioOpt)
# These act as a baseline prior before dynamically incorporating forward-test results.
BASELINE_EXPECTED_RETURN = 0.10
BASELINE_CONFIDENCE = 0.50

# Constraints
MIN_RR = 2.0


def aggregate_candidates(candidates):
    """
    Deterministically aggregates candidates by symbol to avoid dropping consensus information.
    Validates entry, stop loss, target, and RR.
    """
    agg = {}
    
    for c in candidates:
        sym = c.get("symbol")
        if not sym or str(sym) == "0":
            continue
            
        entry = float(c.get("entry_price") or 0)
        sl = float(c.get("stop_loss") or 0)
        target = float(c.get("target") or 0)
        strat = c.get("strategy_name")
        
        # Risk Reward Validation
        if entry > 0 and sl > 0 and target > 0 and entry > sl:
            risk = entry - sl
            reward = target - entry
            rr = reward / risk
        else:
            rr = 0
            
        if sym not in agg:
            agg[sym] = {
                "symbol": sym,
                "entry_price": entry,
                "stop_loss": sl,
                "target": target,
                "rr": rr,
                "strategies": set(),
                "original_candidates": []
            }
            
        agg[sym]["strategies"].add(strat)
        agg[sym]["original_candidates"].append(c)
        
    # Finalize
    final_candidates = []
    for sym in sorted(agg.keys()):
        data = agg[sym]
        strats = sorted(list(data["strategies"]))
        strat_count = len(strats)
        
        # Simple bounded consensus score.
        # Start at BASELINE_CONFIDENCE, add 0.05 per additional strategy, capped at 0.90.
        consensus_score = min(0.90, BASELINE_CONFIDENCE + (0.05 * (strat_count - 1)))
        
        final_candidates.append({
            "symbol": sym,
            "entry_price": data["entry_price"],
            "stop_loss": data["stop_loss"],
            "target": data["target"],
            "rr": data["rr"],
            "strategy_names": ", ".join(strats),
            "strategy_count": strat_count,
            "strategy_consensus_score": consensus_score
        })
        
    return final_candidates

def build_fallback_allocations(valid_candidates, capital, prices_df=None, reason="Fallback"):
    """
    Deterministically allocates equal weight up to MAX_WEIGHT.
    Retains remaining capital as CASH.
    """
    logger.info(f"Using fallback allocation due to: {reason}")
    
    symbols = sorted([c["symbol"] for c in valid_candidates])
    
    if len(symbols) == 0:
        return [{"Symbol": "CASH", "Target_Weight_Pct": 100.0, "Actual_Weight_Pct": 100.0, 
                 "Allocation_Rs": float(capital), "Suggested_Shares": 1, 
                 "Current_Price": float(capital), "Strategy_Names": "", 
                 "Strategy_Count": 0, "Risk_Reward": 0.0, "Cash_Reason": "No valid candidates"}]
                 
    weight = min(1.0 / len(symbols), MAX_WEIGHT)
    
    
    allocations = []
    total_allocated = 0.0
    max_risk_rupees = capital * MAX_RISK_PER_TRADE_PCT
    
    for c in valid_candidates:
        sym = c["symbol"]
        curr_price = float(prices_df[sym].iloc[-1]) if prices_df is not None and not prices_df.empty else float(c["entry_price"])
        
        allocation_amt = capital * weight
        capital_shares = int(allocation_amt // curr_price) if curr_price > 0 else 0
        
        # Risk-based share limit calculation
        risk_per_share = curr_price - float(c["stop_loss"])
        if risk_per_share > 0:
            risk_allowed_shares = int(max_risk_rupees // risk_per_share)
            if risk_allowed_shares < capital_shares:
                logger.info(f"Risk constraint active for {sym}: Capping shares from {capital_shares} to {risk_allowed_shares}")
            shares = min(capital_shares, risk_allowed_shares)
        else:
            shares = capital_shares
            
        actual_allocation = shares * curr_price
        actual_weight = actual_allocation / capital
        
        allocations.append({
            "Symbol": sym,
            "Target_Weight_Pct": round(weight * 100, 2),
            "Actual_Weight_Pct": round(actual_weight * 100, 2),
            "Allocation_Rs": round(actual_allocation, 2),
            "Suggested_Shares": shares,
            "Current_Price": round(curr_price, 2),
            "Strategy_Names": c["strategy_names"],
            "Strategy_Count": c["strategy_count"],
            "Risk_Reward": round(c["rr"], 2),
            "Cash_Reason": ""
        })
        total_allocated += actual_allocation
        
    cash = capital - total_allocated
    
    cash_reason = reason
    if len(symbols) < (1.0 / MAX_WEIGHT):
        cash_reason = f"Max Position Constraint ({len(symbols)} candidates)"
    elif cash > 0:
        cash_reason = "Share Rounding Remainder"
        
    allocations.append({
        "Symbol": "CASH",
        "Target_Weight_Pct": round((cash / capital) * 100, 2),
        "Actual_Weight_Pct": round((cash / capital) * 100, 2),
        "Allocation_Rs": round(cash, 2),
        "Suggested_Shares": 1,
        "Current_Price": round(cash, 2),
        "Strategy_Names": "",
        "Strategy_Count": 0,
        "Risk_Reward": 0.0,
        "Cash_Reason": cash_reason
    })
    
    return sorted(allocations, key=lambda x: x["Actual_Weight_Pct"], reverse=True)


def optimize_portfolio(candidates, as_of_date, capital=1_000_000):
    """
    Takes a list of candidate dictionaries.
    Aggregates candidates, checks historical risk profiles, constructs unbiased BL views,
    and returns deterministic allocation weights.
    """
    if not candidates:
        return []
        
    agg_candidates = aggregate_candidates(candidates)
    
    if not agg_candidates:
        return []
        
    symbols = [c["symbol"] for c in agg_candidates]
    
    # 1. Fetch historical data strictly through as_of_date to prevent look-ahead bias
    logger.info(f"Fetching historical data for {len(symbols)} candidates through {as_of_date}...")
    bulk_data = fetch_bulk_history(symbols, as_of_date, lookback_days=PORTFOLIO_LOOKBACK_DAYS)
    
    price_dict = {}
    excluded_symbols = []
    
    for sym in symbols:
        if sym in bulk_data and not bulk_data[sym].empty:
            if len(bulk_data[sym]) >= MIN_HISTORY_DAYS:
                price_dict[sym] = bulk_data[sym]['Close']
            else:
                excluded_symbols.append((sym, "Insufficient history"))
        else:
            excluded_symbols.append((sym, "No history found"))
            
    if excluded_symbols:
        logger.warning(f"Excluded {len(excluded_symbols)} symbols due to data quality: {excluded_symbols}")
        
    valid_symbols = list(price_dict.keys())
    valid_candidates = [c for c in agg_candidates if c["symbol"] in valid_symbols]
    
    if not valid_candidates:
        logger.error("No valid candidates remaining after data quality checks.")
        return build_fallback_allocations([], capital, reason="Data Exclusion")
        
    prices = pd.DataFrame(price_dict)
    
    # Forward fill only small internal gaps to avoid fabricating history
    prices.ffill(limit=5, inplace=True)
    prices.dropna(inplace=True)
    
    if prices.empty or prices.shape[1] < 2:
        logger.warning(f"Not enough valid asset history for covariance optimization. Fallback triggered.")
        return build_fallback_allocations(valid_candidates, capital, prices_df=prices, reason="Insufficient assets for Covariance")

    # If N < minimum required for fully invested portfolio, fallback
    # Because EfficientFrontier requires sum(weights) == 1, 
    # if N < ceil(1/MAX_WEIGHT), it is mathematically infeasible to solve.
    min_assets_required = int(np.ceil(1.0 / MAX_WEIGHT))
    if len(valid_candidates) < min_assets_required:
        logger.info(f"Fewer than {min_assets_required} candidates available. Black-Litterman optimization is infeasible due to MAX_WEIGHT constraints. Falling back to deterministic weighting.")
        return build_fallback_allocations(valid_candidates, capital, prices_df=prices, reason=f"N < {min_assets_required} Assets Feasibility")

    # 2. Risk Models and Expected Returns (Priors)
    try:
        if COVARIANCE_METHOD == "ledoit_wolf":
            S = risk_models.CovarianceShrinkage(prices).ledoit_wolf()
        else:
            S = risk_models.sample_cov(prices)
            
        pi = expected_returns.mean_historical_return(prices)
    except Exception as e:
        logger.error(f"Error calculating risk models: {e}. Fallback triggered.")
        return build_fallback_allocations(valid_candidates, capital, prices_df=prices, reason="Covariance Error")
        
    # 3. Construct Views & Confidences Safely aligned with prices columns
    ordered_symbols = list(prices.columns)
    view_dict = {}
    conf_dict = {}
    
    for sym in ordered_symbols:
        c = next(cand for cand in valid_candidates if cand["symbol"] == sym)
        view_dict[sym] = BASELINE_EXPECTED_RETURN
        conf_dict[sym] = c["strategy_consensus_score"]
        
    confidences = [conf_dict[sym] for sym in ordered_symbols]
    
    # 4. Black-Litterman Model
    try:
        bl = BlackLittermanModel(
            S, 
            pi=pi, 
            absolute_views=view_dict, 
            omega="idzorek", 
            view_confidences=confidences
        )
        
        rets = bl.bl_returns()
        cov = bl.bl_cov()
        
        # 5. Optimize
        ef = EfficientFrontier(rets, cov, weight_bounds=(0, MAX_WEIGHT))
        
        try:
            weights = ef.max_sharpe()
        except Exception as ms_err:
            logger.warning(f"Max Sharpe failed ({ms_err}), falling back to Min Volatility.")
            weights = ef.min_volatility()
            
        cleaned_weights = ef.clean_weights()
        
    except Exception as e:
        logger.error(f"Black-Litterman optimization failed: {e}. Falling back to deterministic weights.")
        return build_fallback_allocations(valid_candidates, capital, prices_df=prices, reason="BL Optimization Error")
        
    # 6. Allocation Accounting
    allocations = []
    total_allocated = 0.0
    max_risk_rupees = capital * MAX_RISK_PER_TRADE_PCT
    
    for sym, target_weight in cleaned_weights.items():
        if target_weight > MIN_POSITION_WEIGHT:
            c = next(cand for cand in valid_candidates if cand["symbol"] == sym)
            curr_price = float(prices[sym].iloc[-1])
            
            allocation_amt = capital * target_weight
            capital_shares = int(allocation_amt // curr_price) if curr_price > 0 else 0
            
            # Risk-based share limit calculation
            risk_per_share = curr_price - float(c["stop_loss"])
            if risk_per_share > 0:
                risk_allowed_shares = int(max_risk_rupees // risk_per_share)
                if risk_allowed_shares < capital_shares:
                    logger.info(f"Risk constraint active for {sym}: Capping shares from {capital_shares} to {risk_allowed_shares}")
                shares = min(capital_shares, risk_allowed_shares)
            else:
                shares = capital_shares
                
            actual_allocation = shares * curr_price
            actual_weight = actual_allocation / capital
            
            allocations.append({
                "Symbol": sym,
                "Target_Weight_Pct": round(target_weight * 100, 2),
                "Actual_Weight_Pct": round(actual_weight * 100, 2),
                "Allocation_Rs": round(actual_allocation, 2),
                "Suggested_Shares": shares,
                "Current_Price": round(curr_price, 2),
                "Strategy_Names": c["strategy_names"],
                "Strategy_Count": c["strategy_count"],
                "Risk_Reward": round(c["rr"], 2),
                "Cash_Reason": ""
            })
            total_allocated += actual_allocation
            
    cash = capital - total_allocated
    
    cash_reason = "Share Rounding Remainder"
    if any(w for w in cleaned_weights.values() if w <= MIN_POSITION_WEIGHT and w > 0):
        cash_reason = "Optimizer assigned low weights + Rounding"
        
    allocations.append({
        "Symbol": "CASH",
        "Target_Weight_Pct": round((cash / capital) * 100, 2),
        "Actual_Weight_Pct": round((cash / capital) * 100, 2),
        "Allocation_Rs": round(cash, 2),
        "Suggested_Shares": 1,
        "Current_Price": round(cash, 2),
        "Strategy_Names": "",
        "Strategy_Count": 0,
        "Risk_Reward": 0.0,
        "Cash_Reason": cash_reason
    })
    
    return sorted(allocations, key=lambda x: x["Actual_Weight_Pct"], reverse=True)
