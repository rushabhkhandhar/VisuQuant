import os
import pandas as pd
import numpy as np
from datetime import datetime

def calculate_and_log_metrics(strategy_name, config, trades, daily_equity, output_dir="."):
    """
    Calculates advanced performance metrics and logs them to a central CSV.
    
    daily_equity: list of dicts [{"Date": date, "Equity": float}, ...]
    trades: list of dicts (the generated trades)
    """
    if not daily_equity:
        return None
        
    equity_df = pd.DataFrame(daily_equity)
    equity_df['Date'] = pd.to_datetime(equity_df['Date'])
    equity_df.set_index('Date', inplace=True)
    
    trades_df = pd.DataFrame(trades)
    total_trades = len(trades_df)
    win_rate = (trades_df['Net_PnL'] > 0).mean() * 100 if total_trades > 0 else 0
    
    # Daily Returns
    equity_df['Daily_Return'] = equity_df['Equity'].pct_change()
    
    # Profit & CAGR
    start_equity = equity_df['Equity'].iloc[0]
    final_equity = equity_df['Equity'].iloc[-1]
    overall_profit = final_equity - start_equity
    
    days = (equity_df.index[-1] - equity_df.index[0]).days
    years = days / 365.25 if days > 0 else 1
    cagr = ((final_equity / start_equity) ** (1 / years)) - 1 if start_equity > 0 else 0
    
    # Max Drawdown
    equity_df['Peak'] = equity_df['Equity'].cummax()
    equity_df['Drawdown'] = (equity_df['Equity'] - equity_df['Peak']) / equity_df['Peak']
    max_drawdown = equity_df['Drawdown'].min()
    
    # Sharpe & Sortino
    mean_daily_return = equity_df['Daily_Return'].mean()
    std_daily_return = equity_df['Daily_Return'].std()
    
    sharpe_ratio = 0
    if std_daily_return > 0:
        sharpe_ratio = (mean_daily_return / std_daily_return) * np.sqrt(252)
        
    negative_returns = equity_df[equity_df['Daily_Return'] < 0]['Daily_Return']
    sortino_ratio = 0
    if len(negative_returns) > 0 and negative_returns.std() > 0:
        sortino_ratio = (mean_daily_return / negative_returns.std()) * np.sqrt(252)
        
    # Calmar Ratio
    calmar_ratio = 0
    if max_drawdown < 0:
        calmar_ratio = cagr / abs(max_drawdown)
        
    # Monthly returns
    monthly_equity = equity_df['Equity'].resample('ME').last()
    monthly_returns = monthly_equity.pct_change().dropna()
    avg_monthly_return = monthly_returns.mean() * 100 if len(monthly_returns) > 0 else 0
    max_monthly_drawdown = monthly_returns.min() * 100 if len(monthly_returns) > 0 else 0
    
    metrics = {
        "Timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Strategy": strategy_name,
        "Risk ATR": config.get('atr_stop_loss_multiplier', ''),
        "Reward ATR": config.get('target_r_multiple', ''),
        "Sizing logic": f"Risk {config.get('risk_per_trade_pct', 0)*100}%",
        "Regime Filter": "Index/Sector Trend" if 'rvol_lookback_days' not in config else "Intraday RVol",
        "Overall Profit (Rs)": round(overall_profit, 2),
        "CAGR (%)": round(cagr * 100, 2),
        "Max Drawdown (%)": round(max_drawdown * 100, 2),
        "Win Rate (%)": round(win_rate, 2),
        "Sharpe Ratio": round(sharpe_ratio, 2),
        "Sortino Ratio": round(sortino_ratio, 2),
        "Calmar Ratio": round(calmar_ratio, 2),
        "Total Trades": total_trades,
        "Avg Monthly Return (%)": round(avg_monthly_return, 2),
        "Max Monthly Drawdown (%)": round(max_monthly_drawdown, 2)
    }
    
    # Save to CSV
    csv_path = os.path.join(output_dir, "strategy_performance_log.csv")
    df = pd.DataFrame([metrics])
    
    if os.path.exists(csv_path):
        df.to_csv(csv_path, mode='a', header=False, index=False)
    else:
        df.to_csv(csv_path, index=False)
        
    return metrics
