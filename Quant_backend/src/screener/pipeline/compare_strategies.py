import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import date, timedelta
import talib

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols, load_nifty500_industry_mapping
from src.screener.pipeline.run_front_test import (
    trend_pullback_eval,
    momentum_breakout_eval,
    oversold_uptrend_eval,
    volatility_compression_eval,
    relative_strength_eval
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

INITIAL_CAPITAL = 1_00_000.0
MAX_WEIGHT_PER_TRADE = 0.20  # Max 20% of total equity per trade
FRICTION_PCT = 0.0015  # 0.15% cost per trade leg

STRATEGIES = [
    # {"name": "Trend Pullback", "func": trend_pullback_eval, "risk_atr": 1.5, "reward_atr": 3.0},
    {"name": "Momentum Breakout", "func": momentum_breakout_eval, "risk_atr": 2.0, "reward_atr": 4.0},
    # {"name": "Oversold Uptrend", "func": oversold_uptrend_eval, "risk_atr": 2.0, "reward_atr": 4.0},
    {"name": "Volatility Compression", "func": volatility_compression_eval, "risk_atr": 1.0, "reward_atr": 3.0},
    {"name": "Relative Strength", "func": relative_strength_eval, "risk_atr": 2.0, "reward_atr": 4.0},
]

def calculate_metrics(daily_equity, trades):
    # Daily Returns
    equity_series = pd.Series(daily_equity)
    daily_returns = equity_series.pct_change().dropna()
    
    # CAGR
    years = len(daily_equity) / 252.0
    if years > 0 and equity_series.iloc[0] > 0:
        cagr = ((equity_series.iloc[-1] / equity_series.iloc[0]) ** (1 / years) - 1) * 100
    else:
        cagr = 0.0
        
    # MDD
    cumulative = equity_series
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    mdd = drawdown.min() * 100
    
    # Ratios
    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std()
    downside_std = daily_returns[daily_returns < 0].std()
    
    sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0
    sortino = (mean_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 0
    calmar = (cagr / abs(mdd)) if mdd < 0 else 0
    
    # Trades
    wins = [t for t in trades if t['pnl_pct'] > 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    overall_profit = equity_series.iloc[-1] - INITIAL_CAPITAL
    
    return {
        "Overall Profit (Rs)": round(overall_profit, 2),
        "CAGR (%)": round(cagr, 2),
        "Max Drawdown (%)": round(mdd, 2),
        "Win Rate (%)": round(win_rate, 2),
        "Sharpe Ratio": round(sharpe, 3),
        "Sortino Ratio": round(sortino, 3),
        "Calmar Ratio": round(calmar, 3),
        "Total Trades": len(trades)
    }

def run_strategy_backtest(strategy, test_dates, bulk_data, industry_mapping=None, sector_indices=None):
    logger.info(f"Backtesting {strategy['name']}...")
    
    cash = INITIAL_CAPITAL
    open_positions = {}
    daily_equity_curve = []
    trades_log = []
    
    for i, current_date in enumerate(test_dates):
        # 1. Update prices and check exits
        symbols_to_remove = []
        for sym, pos in open_positions.items():
            if sym in bulk_data:
                df = bulk_data[sym]
                if current_date in df.index:
                    row = df.loc[current_date]
                    
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[-1]
                        
                    high = row['High']
                    low = row['Low']
                    close = row['Close']
                    
                    pos['current_price'] = close
                    
                    # Exit logic
                    if low <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Loss"})
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Win"})
                        
        for sym in symbols_to_remove:
            del open_positions[sym]
            
        # 2. Evaluate new candidates if we have cash
        new_candidates = []
        if cash > (INITIAL_CAPITAL * 0.05): # Minimum 5% cash to bother looking for trades
            nifty_hist = None
            if "NIFTYBEES" in bulk_data:
                nifty_df = bulk_data["NIFTYBEES"]
                if current_date in nifty_df.index:
                    nifty_hist = nifty_df[nifty_df.index <= current_date]

            for sym, df in bulk_data.items():
                if sym == "NIFTYBEES":
                    continue
                if sym in open_positions:
                    continue
                    
                # Slice history up to current date
                hist_df = df[df.index <= current_date]
                if len(hist_df) < 200:
                    continue
                    
                # Run eval
                try:
                    sector_hist = None
                    if industry_mapping and sector_indices and sym in industry_mapping:
                        ind = industry_mapping[sym]
                        if ind in sector_indices:
                            sector_hist = sector_indices[ind][sector_indices[ind].index <= current_date]
                            
                    res = strategy['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist)
                    if res.get('passed', False):
                        close = hist_df['Close'].iloc[-1]
                        atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                        
                        if pd.notna(atr) and atr > 0:
                            new_candidates.append({
                                "symbol": sym,
                                "price": close,
                                "stop_loss": close - (atr * strategy['risk_atr']),
                                "target": close + (atr * strategy['reward_atr'])
                            })
                except Exception as e:
                    pass # Skip if eval fails
                    
        # 3. Allocate Cash
        if new_candidates:
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE
            
            for cand in new_candidates:
                # Volatility sizing: Risk 2% of total equity
                risk_amount = total_equity * 0.02
                risk_per_share = cand['price'] - cand['stop_loss']
                
                if risk_per_share <= 0:
                    continue
                    
                ideal_shares = int(risk_amount / risk_per_share)
                
                # Cap the trade value to MAX_WEIGHT_PER_TRADE
                max_shares = int(max_alloc_per_trade / cand['price'])
                shares = min(ideal_shares, max_shares)
                
                required_cash = shares * cand['price'] * (1 + FRICTION_PCT)
                
                if shares > 0 and cash >= required_cash:
                    cash -= required_cash
                    open_positions[cand['symbol']] = {
                        "shares": shares,
                        "entry_price": cand['price'],
                        "current_price": cand['price'],
                        "stop_loss": cand['stop_loss'],
                        "target": cand['target']
                    }
                        
        # 4. Record Daily Equity
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_equity_curve.append(total_equity)
        
    metrics = calculate_metrics(daily_equity_curve, trades_log)
    metrics["Strategy"] = strategy["name"]
    return metrics, daily_equity_curve



def run_ensemble_backtest(strategies, test_dates, bulk_data, industry_mapping=None, sector_indices=None):
    logger.info(f"Backtesting Ensemble (Combined)...")
    
    cash = INITIAL_CAPITAL
    open_positions = {}
    daily_equity_curve = []
    trades_log = []
    
    for i, current_date in enumerate(test_dates):
        # 1. Update prices and check exits
        symbols_to_remove = []
        for sym, pos in open_positions.items():
            if sym in bulk_data:
                df = bulk_data[sym]
                if current_date in df.index:
                    row = df.loc[current_date]
                    
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[-1]
                        
                    high = row['High']
                    low = row['Low']
                    close = row['Close']
                    
                    pos['current_price'] = close
                    
                    # Exit logic
                    if low <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Loss"})
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Win"})
                        
        for sym in symbols_to_remove:
            del open_positions[sym]
            
        # 2. Evaluate new candidates if we have cash
        new_candidates = []
        if cash > (INITIAL_CAPITAL * 0.05): # Minimum 5% cash to bother looking for trades
            nifty_hist = None
            if "NIFTYBEES" in bulk_data:
                nifty_df = bulk_data["NIFTYBEES"]
                if current_date in nifty_df.index:
                    nifty_hist = nifty_df[nifty_df.index <= current_date]

            for sym, df in bulk_data.items():
                if sym == "NIFTYBEES":
                    continue
                if sym in open_positions:
                    continue
                    
                # Slice history up to current date
                hist_df = df[df.index <= current_date]
                if len(hist_df) < 200:
                    continue
                    
                # Run eval for all strategies
                for strategy in strategies:
                    try:
                        sector_hist = None
                        if industry_mapping and sector_indices and sym in industry_mapping:
                            ind = industry_mapping[sym]
                            if ind in sector_indices:
                                sector_hist = sector_indices[ind][sector_indices[ind].index <= current_date]
                                
                        res = strategy['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist)
                        if res.get('passed', False):
                            close = hist_df['Close'].iloc[-1]
                            atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                            
                            if pd.notna(atr) and atr > 0:
                                new_candidates.append({
                                    "symbol": sym,
                                    "price": close,
                                    "stop_loss": close - (atr * strategy['risk_atr']),
                                    "target": close + (atr * strategy['reward_atr']),
                                    "strategy_name": strategy['name']
                                })
                                break # Do not evaluate further strategies for this symbol if one triggered
                    except Exception as e:
                        pass # Skip if eval fails
                    
        # 3. Allocate Cash
        if new_candidates:
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE
            
            for cand in new_candidates:
                # Volatility sizing: Risk 2% of total equity
                risk_amount = total_equity * 0.02
                risk_per_share = cand['price'] - cand['stop_loss']
                
                if risk_per_share <= 0:
                    continue
                    
                ideal_shares = int(risk_amount / risk_per_share)
                
                # Cap the trade value to MAX_WEIGHT_PER_TRADE
                max_shares = int(max_alloc_per_trade / cand['price'])
                shares = min(ideal_shares, max_shares)
                
                required_cash = shares * cand['price'] * (1 + FRICTION_PCT)
                
                if shares > 0 and cash >= required_cash:
                    cash -= required_cash
                    open_positions[cand['symbol']] = {
                        "shares": shares,
                        "entry_price": cand['price'],
                        "current_price": cand['price'],
                        "stop_loss": cand['stop_loss'],
                        "target": cand['target'],
                        "strategy": cand['strategy_name']
                    }
                        
        # 4. Record Daily Equity
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_equity_curve.append(total_equity)
        
    metrics = calculate_metrics(daily_equity_curve, trades_log)
    metrics["Strategy"] = "Ensemble (Combined)"
    return metrics, daily_equity_curve



def main():
    years = 2
    backtest_days = int(years * 252)
    total_lookback = backtest_days + 300
    
    logger.info(f"Loading NIFTY 500 universe...")
    universe = load_nifty500_symbols()
    if "NIFTYBEES" not in universe:
        universe.append("NIFTYBEES")
    
    logger.info(f"Fetching bulk history for last {total_lookback} days...")
    bulk_data = fetch_bulk_history(universe, date.today(), lookback_days=total_lookback)
    

    
    # Align dates
    all_dates = set()
    for df in bulk_data.values():
        if not df.empty:
            all_dates.update(df.index.tolist())
    sorted_dates = sorted(list(all_dates))
    
    test_dates = sorted_dates[-backtest_days:]
    logger.info(f"Backtesting over {len(test_dates)} trading days...")
    
    results = []
    curves = {}
    
    logger.info("Loading industry mapping and constructing synthetic sector indices...")
    industry_mapping = load_nifty500_industry_mapping()
    
    # Construct sector indices
    sector_indices = {}
    sectors = {}
    for sym, df in bulk_data.items():
        if sym in industry_mapping and not df.empty:
            ind = industry_mapping[sym]
            if ind not in sectors:
                sectors[ind] = []
            # Calculate daily returns for the symbol
            sectors[ind].append(df['Close'].pct_change().fillna(0))
            
    for ind, returns_list in sectors.items():
        # Average return across all stocks in this sector for each day
        avg_returns = pd.concat(returns_list, axis=1).mean(axis=1)
        # Create a synthetic price index starting at 100
        synthetic_price = 100 * (1 + avg_returns).cumprod()
        sector_indices[ind] = pd.DataFrame({"Close": synthetic_price})
    
    for strategy in STRATEGIES:
        metrics, curve = run_strategy_backtest(strategy, test_dates, bulk_data, industry_mapping, sector_indices)
        results.append(metrics)
        curves[strategy['name']] = curve
        
    # Run Ensemble
    ensemble_metrics, ensemble_curve = run_ensemble_backtest(STRATEGIES, test_dates, bulk_data, industry_mapping, sector_indices)
    results.append(ensemble_metrics)
    curves["Ensemble (Combined)"] = ensemble_curve
        
    # Compile Tear Sheet
    results_df = pd.DataFrame(results)
    results_df = results_df.set_index("Strategy")
    results_df = results_df.sort_values(by="Sharpe Ratio", ascending=False)
    
    tear_sheet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))), "front_testing", "strategy_tear_sheet.csv")
    results_df.to_csv(tear_sheet_path)
    
    curves_df = pd.DataFrame(curves, index=test_dates)
    curves_path = os.path.join(os.path.dirname(tear_sheet_path), "strategy_equity_curves.csv")
    curves_df.to_csv(curves_path)
    
    # Append to experiment log
    from datetime import datetime
    experiment_log_path = os.path.join(os.path.dirname(tear_sheet_path), "experiment_log.csv")
    log_records = []
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for r in results:
        record = {
            "Timestamp": timestamp, 
            "Strategy": r["Strategy"], 
            "Risk ATR": 2.0, 
            "Reward ATR": 4.0, 
            "Sizing logic": "Volatility (2% Risk)",
            "Regime Filter": "RS (20d & 60d) > Nifty"
        }
        record.update(r)
        log_records.append(record)
        
    log_df = pd.DataFrame(log_records)
    if os.path.exists(experiment_log_path):
        existing_df = pd.read_csv(experiment_log_path)
        combined_df = pd.concat([existing_df, log_df], ignore_index=True)
        combined_df.fillna("-", inplace=True)
        combined_df.to_csv(experiment_log_path, index=False)
    else:
        log_df.fillna("-", inplace=True)
        log_df.to_csv(experiment_log_path, index=False)
    
    logger.info(f"Tear sheet successfully generated and saved to {tear_sheet_path}")
    logger.info(f"Appended results to {experiment_log_path}")
    print("\n================= STRATEGY TEAR SHEET (LAST 2 YEARS) =================")
    print(results_df.to_string())
    print("======================================================================\n")

if __name__ == "__main__":
    main()
