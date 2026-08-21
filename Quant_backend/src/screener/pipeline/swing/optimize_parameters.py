import os
import sys
import logging
import pandas as pd
import numpy as np
from datetime import date, timedelta
import talib

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols
from src.screener.pipeline.swing.run_front_test import (
    trend_pullback_eval,
    momentum_breakout_eval,
    oversold_uptrend_eval,
    volatility_compression_eval,
    relative_strength_eval
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

INITIAL_CAPITAL = 1_000_000.0
MAX_WEIGHT_PER_TRADE = 0.20

PARAM_GRID = [
    {"sl": 1.0, "tp": 2.0},
    {"sl": 1.5, "tp": 3.0},
    {"sl": 2.0, "tp": 4.0},
    {"sl": 2.5, "tp": 5.0},
    {"sl": 3.0, "tp": 6.0},
]

STRATEGIES = [
    {"name": "Trend Pullback", "func": trend_pullback_eval},
    {"name": "Momentum Breakout", "func": momentum_breakout_eval},
    {"name": "Oversold Uptrend", "func": oversold_uptrend_eval},
    {"name": "Volatility Compression", "func": volatility_compression_eval},
    {"name": "Relative Strength", "func": relative_strength_eval},
]

def calculate_metrics(daily_equity, trades):
    equity_series = pd.Series(daily_equity)
    daily_returns = equity_series.pct_change().dropna()
    
    years = len(daily_equity) / 252.0
    if years > 0 and equity_series.iloc[0] > 0:
        cagr = ((equity_series.iloc[-1] / equity_series.iloc[0]) ** (1 / years) - 1) * 100
    else:
        cagr = 0.0
        
    cumulative = equity_series
    running_max = cumulative.cummax()
    drawdown = (cumulative - running_max) / running_max
    mdd = drawdown.min() * 100
    
    mean_ret = daily_returns.mean()
    std_ret = daily_returns.std()
    downside_std = daily_returns[daily_returns < 0].std()
    
    sharpe = (mean_ret / std_ret) * np.sqrt(252) if std_ret > 0 else 0
    sortino = (mean_ret / downside_std) * np.sqrt(252) if downside_std > 0 else 0
    calmar = (cagr / abs(mdd)) if mdd < 0 else 0
    
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

def run_parameter_backtest(params, strategy, test_dates, bulk_data):
    logger.info(f"Backtesting {strategy['name']} with SL {params['sl']} ATR / Target {params['tp']} ATR...")
    
    cash = INITIAL_CAPITAL
    open_positions = {}
    daily_equity_curve = []
    trades_log = []
    
    for current_date in test_dates:
        symbols_to_remove = []
        for sym, pos in open_positions.items():
            if sym in bulk_data:
                df = bulk_data[sym]
                if current_date in df.index:
                    row = df.loc[current_date]
                    if isinstance(row, pd.DataFrame): row = row.iloc[-1]
                        
                    high, low, close = row['High'], row['Low'], row['Close']
                    pos['current_price'] = close
                    
                    if low <= pos['stop_loss']:
                        pnl = (pos['stop_loss'] - pos['entry_price']) / pos['entry_price']
                        cash += pos['shares'] * pos['stop_loss']
                        symbols_to_remove.append(sym)
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Loss"})
                    elif high >= pos['target']:
                        pnl = (pos['target'] - pos['entry_price']) / pos['entry_price']
                        cash += pos['shares'] * pos['target']
                        symbols_to_remove.append(sym)
                        trades_log.append({"symbol": sym, "pnl_pct": pnl, "status": "Win"})
                        
        for sym in symbols_to_remove: del open_positions[sym]
            
        new_candidates = []
        if cash > (INITIAL_CAPITAL * 0.05):
            for sym, df in bulk_data.items():
                if sym in open_positions: continue
                hist_df = df[df.index <= current_date]
                if len(hist_df) < 200: continue
                    
                try:
                    res = strategy['func'](hist_df)
                    if res.get('passed', False):
                        close = hist_df['Close'].iloc[-1]
                        atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                        
                        if pd.notna(atr) and atr > 0:
                            new_candidates.append({
                                "symbol": sym, "price": close,
                                "stop_loss": close - (atr * params['sl']),
                                "target": close + (atr * params['tp'])
                            })
                except:
                    pass 
                    
        if new_candidates:
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE
            alloc_per_trade = min(cash / len(new_candidates), max_alloc_per_trade)
            
            for cand in new_candidates:
                if cash >= alloc_per_trade and alloc_per_trade > 1000:
                    shares = int(alloc_per_trade // cand['price'])
                    if shares > 0:
                        cash -= shares * cand['price']
                        open_positions[cand['symbol']] = {
                            "shares": shares, "entry_price": cand['price'], "current_price": cand['price'],
                            "stop_loss": cand['stop_loss'], "target": cand['target']
                        }
                        
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_equity_curve.append(total_equity)
        
    metrics = calculate_metrics(daily_equity_curve, trades_log)
    metrics["Strategy"] = strategy['name']
    metrics["Parameters (SL/TP)"] = f"{params['sl']} / {params['tp']}"
    return metrics


def main():
    years = 2
    backtest_days = int(years * 252)
    total_lookback = backtest_days + 300
    
    logger.info(f"Loading NIFTY 500 universe...")
    universe = load_nifty500_symbols()
    
    logger.info(f"Fetching bulk history for last {total_lookback} days...")
    bulk_data = fetch_bulk_history(universe, date.today(), lookback_days=total_lookback)
    
    all_dates = set()
    for df in bulk_data.values():
        if not df.empty: all_dates.update(df.index.tolist())
    sorted_dates = sorted(list(all_dates))
    test_dates = sorted_dates[-backtest_days:]
    
    logger.info(f"Optimizing all strategies over {len(test_dates)} trading days...")
    
    all_results = []
    
    for strategy in STRATEGIES:
        for params in PARAM_GRID:
            metrics = run_parameter_backtest(params, strategy, test_dates, bulk_data)
            all_results.append(metrics)
            
    results_df = pd.DataFrame(all_results)
    results_df = results_df.set_index(["Strategy", "Parameters (SL/TP)"])
    results_df = results_df.sort_values(by=["Strategy", "Sharpe Ratio"], ascending=[True, False])
    
    tear_sheet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing", "optimization_results.csv")
    results_df.to_csv(tear_sheet_path)
    
    logger.info(f"Optimization successfully generated and saved to {tear_sheet_path}")
    print(f"\n============= MASTER PARAMETER OPTIMIZATION =============")
    print(results_df.to_string())
    print("======================================================================\n")

if __name__ == "__main__":
    main()
