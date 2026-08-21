import os
import json
import csv
import logging
from datetime import datetime
import pandas as pd

from src.data.nse_fetcher import fetch_bulk_history
from src.screener.portfolio.portfolio_optimizer import optimize_portfolio

logger = logging.getLogger(__name__)

INITIAL_CAPITAL = 1_00_000.0

def get_paths(strategy_name):
    safe_name = strategy_name.replace(" ", "_").replace("/", "_")
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "front_testing", safe_name)
    os.makedirs(base_dir, exist_ok=True)
    
    state_file = os.path.join(base_dir, "portfolio_state.json")
    log_file = os.path.join(base_dir, "portfolio_performance_log.csv")
    alloc_base = base_dir
    
    return state_file, log_file, alloc_base

def load_portfolio_state(strategy_name):
    state_file, _, _ = get_paths(strategy_name)
    if os.path.exists(state_file):
        try:
            with open(state_file, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load portfolio state for {strategy_name}: {e}")
    
    return {
        "starting_capital": INITIAL_CAPITAL,
        "available_cash": INITIAL_CAPITAL,
        "total_equity_value": INITIAL_CAPITAL,
        "active_positions": {}, 
        "history": []
    }

def save_portfolio_state(state, strategy_name):
    state_file, _, _ = get_paths(strategy_name)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=4)

def log_performance(as_of_date, total_equity, cash_balance, num_positions, strategy_name):
    _, log_file, _ = get_paths(strategy_name)
    file_exists = os.path.exists(log_file)
    
    with open(log_file, "a", newline="") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(["Date", "Total_Equity", "Cash_Balance", "Number_of_Positions"])
        writer.writerow([as_of_date.strftime("%Y-%m-%d"), round(total_equity, 2), round(cash_balance, 2), num_positions])

def step_portfolio(todays_candidates, as_of_date, strategy_name):
    """
    Executes a single day's step in the continuous portfolio.
    1. Updates prices for existing positions.
    2. Executes Stop Losses / Profit Targets.
    3. Merges remaining positions with todays_candidates.
    4. Runs Black-Litterman optimization to rebalance.
    """
    state_file, log_file, alloc_base = get_paths(strategy_name)
    state = load_portfolio_state(strategy_name)
    date_str = as_of_date.strftime("%Y-%m-%d")
    
    logger.info(f"Stepping portfolio tracker for {strategy_name} on {date_str}...")
    
    # 1. Update Prices & Execute Stops
    active_positions = state["active_positions"]
    
    if active_positions:
        symbols_to_update = list(active_positions.keys())
        # fetch_bulk_history requires at least 10 days of data to return a dataframe
        bulk_data = fetch_bulk_history(symbols_to_update, as_of_date, lookback_days=15)
        
        symbols_to_remove = []
        
        for sym, pos in active_positions.items():
            if sym in bulk_data and not bulk_data[sym].empty:
                close_price = float(bulk_data[sym]['Close'].iloc[-1])
                pos["current_price"] = close_price
                
                if close_price <= pos["stop_loss"]:
                    logger.info(f"PORTFOLIO EXIT: {sym} hit Stop Loss at {close_price} (SL: {pos['stop_loss']})")
                    state["available_cash"] += pos["shares"] * close_price
                    symbols_to_remove.append(sym)
                elif close_price >= pos["target"]:
                    logger.info(f"PORTFOLIO EXIT: {sym} hit Profit Target at {close_price} (Target: {pos['target']})")
                    state["available_cash"] += pos["shares"] * close_price
                    symbols_to_remove.append(sym)
            else:
                logger.warning(f"No price data found to update portfolio position for {sym}.")
                
        for sym in symbols_to_remove:
            del active_positions[sym]
            
    positions_value = sum(pos["shares"] * pos["current_price"] for pos in active_positions.values())
    total_equity = state["available_cash"] + positions_value
    state["total_equity_value"] = total_equity
    
    logger.info(f"Pre-Rebalance Equity: {total_equity:.2f} (Cash: {state['available_cash']:.2f}, Positions: {positions_value:.2f})")
    
    # 2. Build Candidate Universe (Cash Deployment Only)
    combined_candidates = []
    
    for c in todays_candidates:
        sym = str(c.get("symbol", ""))
        # Only deploy cash into NEW candidates that we don't already hold
        if sym and sym != "0" and sym not in active_positions:
            combined_candidates.append(c)
        
    if not combined_candidates or state["available_cash"] < 1000:
        logger.info("No new candidates or insufficient cash. Holding current positions.")
        save_portfolio_state(state, strategy_name)
        log_performance(as_of_date, total_equity, state["available_cash"], len(active_positions), strategy_name)
        return
        
    # 3. Run Optimization (Cash Only)
    logger.info(f"Running Cash Deployment Optimization on {len(combined_candidates)} new signals with Rs {state['available_cash']:.2f}...")
    allocations = optimize_portfolio(combined_candidates, as_of_date, capital=state["available_cash"])
    
    if not allocations:
        logger.warning("Optimizer returned no allocations. Cash remains idle.")
    else:
        # 4. Execute Additions to Portfolio
        new_cash = state["available_cash"]
        
        symbol_map = {}
        for c in combined_candidates:
            symbol_map[c["symbol"]] = c
                
        for alloc in allocations:
            sym = alloc["Symbol"]
            if sym == "CASH":
                new_cash = alloc["Allocation_Rs"]
                continue
                
            shares = alloc["Suggested_Shares"]
            if shares > 0:
                c = symbol_map[sym]
                # Add to existing active positions
                active_positions[sym] = {
                    "shares": shares,
                    "entry_price": alloc["Current_Price"], 
                    "current_price": alloc["Current_Price"],
                    "stop_loss": float(c["stop_loss"]),
                    "target": float(c["target"]),
                    "strategy": alloc["Strategy_Names"]
                }
                
        state["active_positions"] = active_positions
        state["available_cash"] = new_cash
        
    final_positions_value = sum(pos["shares"] * pos["current_price"] for pos in state["active_positions"].values())
    final_equity = state["available_cash"] + final_positions_value
    state["total_equity_value"] = final_equity
    
    logger.info(f"Post-Rebalance Equity: {final_equity:.2f} (Cash: {state['available_cash']:.2f}, Positions: {final_positions_value:.2f})")
    
    save_portfolio_state(state, strategy_name)
    log_performance(as_of_date, final_equity, state["available_cash"], len(state["active_positions"]), strategy_name)
    
    alloc_csv_path = os.path.join(alloc_base, f"portfolio_allocation_{date_str}.csv")
    if allocations:
        keys = allocations[0].keys()
        with open(alloc_csv_path, 'w', newline='') as f:
            dict_writer = csv.DictWriter(f, keys)
            dict_writer.writeheader()
            dict_writer.writerows(allocations)
        logger.info(f"Exported Rebalanced Portfolio Allocations to {alloc_csv_path}")
        
        print("\n================= TODAY'S PORTFOLIO ALLOCATION (BLACK-LITTERMAN REBALANCED) =================")
        for alloc in allocations:
            if alloc['Symbol'] == "CASH":
                print(f"CASH            | Weight: {alloc['Target_Weight_Pct']:>5}% | Shares: {alloc['Suggested_Shares']:>4} | Rs: {alloc['Allocation_Rs']}")
            else:
                print(f"{alloc['Symbol']:<15} | Weight: {alloc['Target_Weight_Pct']:>5}% | Shares: {alloc['Suggested_Shares']:>4} | Rs: {alloc['Allocation_Rs']}")
        print("=============================================================================================\n")
