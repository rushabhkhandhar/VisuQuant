import os
import sys
import logging
import hashlib
import json
import pandas as pd
import numpy as np
from datetime import date, timedelta
import talib

# Add the project root to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols, load_nifty500_industry_mapping
from src.screener.pipeline.swing.run_front_test import (
    trend_pullback_eval,
    momentum_breakout_eval,
    oversold_uptrend_eval,
    volatility_compression_eval,
    relative_strength_eval,
    pocket_pivot_eval,
    connors_rsi_eval,
    ttm_squeeze_eval,
    sector_pullback_eval,
    avwap_pullback_eval,
    dual_avwap_pullback_eval,
    volume_surge_avwap_eval,
    dual_avwap_volume_surge_eval,
    leader_consolidation_eval,
    breadth_thrust_eval
)
from src.screener.pipeline.swing.e19_strategy import (
    BCR_THRESHOLD, BREADTH_THRESHOLD, MAX_CONFIRMED_SIGNALS, MAX_PRIMARY_SIGNALS,
    RISK_ATR, REWARD_ATR, RISK_CONFIRMED, RISK_PRIMARY, MAX_HOLDING_SESSIONS
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

INITIAL_CAPITAL = 1_00_000.0  # 1 Lakh initial capital
MAX_WEIGHT_PER_TRADE = 0.20  # Max 20% of total equity per trade
FRICTION_PCT = 0.0015  # 0.15% cost per trade leg
HOLDOUT_START = pd.Timestamp("2024-08-25")

STRATEGIES = [
    # All standalone strategies paused to focus strictly on architectural candidates:
    # {"name": "Connors RSI-2 Dip", "func": connors_rsi_eval, "risk_atr": 1.5, "reward_atr": 3.0},
    # {"name": "TTM Squeeze", "func": ttm_squeeze_eval, "risk_atr": 1.0, "reward_atr": 3.0},
    # {"name": "Sector Relative Pullback", "func": sector_pullback_eval, "risk_atr": 1.5, "reward_atr": 3.5},
]

def calculate_metrics(daily_equity, trades, test_dates=None):
    # Daily Returns
    if test_dates is not None and len(test_dates) == len(daily_equity):
        equity_series = pd.Series(daily_equity, index=pd.to_datetime(test_dates))
    elif isinstance(daily_equity, pd.Series) and isinstance(daily_equity.index, pd.DatetimeIndex):
        equity_series = daily_equity
    else:
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
    
    # Monthly Return Analytics
    avg_monthly_return = 0.0
    compounded_monthly = 0.0
    monthly_win_rate = 0.0
    best_month = 0.0
    worst_month = 0.0
    if isinstance(equity_series.index, pd.DatetimeIndex) and len(equity_series) > 20:
        try:
            monthly_series = equity_series.resample('ME').last()
        except Exception:
            monthly_series = equity_series.resample('M').last()
        monthly_returns = monthly_series.pct_change().dropna()
        if len(monthly_returns) > 0:
            num_months = len(monthly_returns)
            avg_monthly_return = monthly_returns.mean() * 100.0
            if equity_series.iloc[0] > 0 and num_months > 0:
                compounded_monthly = ((equity_series.iloc[-1] / equity_series.iloc[0]) ** (1.0 / num_months) - 1.0) * 100.0
            else:
                compounded_monthly = avg_monthly_return
            m_wins = monthly_returns[monthly_returns > 0]
            monthly_win_rate = (len(m_wins) / len(monthly_returns)) * 100.0
            best_month = monthly_returns.max() * 100.0
            worst_month = monthly_returns.min() * 100.0
    
    # Trades & Trade-Level Diagnostics
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    overall_profit = equity_series.iloc[-1] - equity_series.iloc[0]
    
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
    
    gross_win = sum([t['pnl_pct'] for t in wins]) if wins else 0
    gross_loss = abs(sum([t['pnl_pct'] for t in losses])) if losses else 0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99 if gross_win > 0 else 0)
    
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * abs(avg_loss))
    turnover = sum([t['entry_price'] * t.get('shares', 1) for t in trades]) / INITIAL_CAPITAL
    
    return {
        "Overall Profit (Rs)": round(overall_profit, 2),
        "CAGR (%)": round(cagr, 2),
        "Net Avg Monthly Return (%)": round(avg_monthly_return, 2),
        "Compounded Monthly Return (%)": round(compounded_monthly, 2),
        "Monthly Win Rate (%)": round(monthly_win_rate, 2),
        "Best Month (%)": round(best_month, 2),
        "Worst Month (%)": round(worst_month, 2),
        "Max Drawdown (%)": round(mdd, 2),
        "Sharpe Ratio": round(sharpe, 3),
        "Sortino Ratio": round(sortino, 3),
        "Calmar Ratio": round(calmar, 3),
        "Total Trades": len(trades),
        "Win Rate (%)": round(win_rate, 2),
        "Profit Factor": round(profit_factor, 3),
        "Expectancy (%)": round(expectancy * 100, 3) if expectancy else 0.0,
        "Avg Win (%)": round(avg_win * 100, 2),
        "Avg Loss (%)": round(avg_loss * 100, 2),
        "Turnover": round(turnover, 2)
    }

def calculate_regime_metrics(trades, nifty_df):
    if nifty_df is None or nifty_df.empty or not trades:
        return {}
        
    # Calculate Nifty Regimes
    nifty_df = nifty_df.copy()
    nifty_df['SMA50'] = nifty_df['Close'].rolling(50).mean()
    nifty_df['SMA200'] = nifty_df['Close'].rolling(200).mean()
    
    # Bullish: Close > 50 and 50 > 200
    # Bearish: Close < 50 and 50 < 200
    # Sideways: Everything else
    conditions = [
        (nifty_df['Close'] > nifty_df['SMA50']) & (nifty_df['SMA50'] > nifty_df['SMA200']),
        (nifty_df['Close'] < nifty_df['SMA50']) & (nifty_df['SMA50'] < nifty_df['SMA200'])
    ]
    choices = ['Bullish', 'Bearish']
    nifty_df['Regime'] = np.select(conditions, choices, default='Sideways')
    
    regime_dict = nifty_df['Regime'].to_dict() # index is timestamp
    
    regimes = {'Bullish': [], 'Bearish': [], 'Sideways': []}
    
    for t in trades:
        # Assign regime based on entry date
        entry_date = pd.Timestamp(t['entry_date'])
        regime = regime_dict.get(entry_date, 'Sideways')
        regimes[regime].append(t)
        
    metrics = {}
    for regime, r_trades in regimes.items():
        if not r_trades:
            metrics[f"{regime} Win Rate"] = 0
            metrics[f"{regime} Trades"] = 0
            continue
            
        wins = [t for t in r_trades if t['pnl_pct'] > 0]
        win_rate = (len(wins) / len(r_trades)) * 100
        metrics[f"{regime} Win Rate"] = round(win_rate, 2)
        metrics[f"{regime} Trades"] = len(r_trades)
        
    return metrics


def summarize_equity_period(strategy_name, equity_curve, dates, period_name, start, end=None):
    """Return an auditable, calendar-time performance summary for one period."""
    series = pd.Series(equity_curve, index=pd.to_datetime(dates), dtype=float)
    period = series[series.index >= pd.Timestamp(start)]
    if end is not None:
        period = period[period.index < pd.Timestamp(end)]
    if len(period) < 2:
        return None

    years = max((period.index[-1] - period.index[0]).days / 365.25, 1 / 365.25)
    total_return = period.iloc[-1] / period.iloc[0] - 1
    cagr = (period.iloc[-1] / period.iloc[0]) ** (1 / years) - 1
    drawdown = period / period.cummax() - 1
    
    # Period Monthly Returns
    try:
        m_series = period.resample('ME').last()
    except Exception:
        m_series = period.resample('M').last()
    m_returns = m_series.pct_change().dropna()
    num_m = len(m_returns)
    avg_m = m_returns.mean() * 100.0 if num_m > 0 else 0.0
    m_win_rate = ((m_returns > 0).mean() * 100.0) if num_m > 0 else 0.0

    return {
        "Strategy": strategy_name,
        "Period": period_name,
        "Start": period.index[0].date().isoformat(),
        "End": period.index[-1].date().isoformat(),
        "Sessions": len(period),
        "Start Equity": round(period.iloc[0], 2),
        "End Equity": round(period.iloc[-1], 2),
        "Total Return (%)": round(total_return * 100, 2),
        "CAGR (%)": round(cagr * 100, 2),
        "Net Avg Monthly Return (%)": round(avg_m, 2),
        "Monthly Win Rate (%)": round(m_win_rate, 2),
        "Max Drawdown (%)": round(drawdown.min() * 100, 2),
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
                        
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "pnl_pct": pnl, 
                            "status": "Loss"
                        })
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "pnl_pct": pnl, 
                            "status": "Win"
                        })
                        
        for sym in symbols_to_remove:
            del open_positions[sym]
            
        # 2. Evaluate new candidates (MOC execution: signal + entry at ~3:15 PM Close)
        new_candidates = []
        if cash > (INITIAL_CAPITAL * 0.05):
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
                                "target": close + (atr * strategy['reward_atr']),
                                "alpha_score": res.get("alpha_score", 0.0)
                            })
                except Exception as e:
                    pass # Skip if eval fails
                    
        # 3. Allocate Cash (MOC entry at Close price, prioritizing highest alpha)
        if new_candidates:
            new_candidates.sort(key=lambda x: x.get("alpha_score", 0.0), reverse=True)
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE
            
            for cand in new_candidates:
                # Volatility sizing: Risk 2% of total equity
                risk_amount = total_equity * 0.02
                risk_per_share = cand['price'] - cand['stop_loss']
                
                if risk_per_share <= 0:
                    continue
                    
                ideal_shares = int(risk_amount / risk_per_share)
                max_shares = int(max_alloc_per_trade / cand['price'])
                shares = min(ideal_shares, max_shares)
                
                required_cash = shares * cand['price'] * (1 + FRICTION_PCT)
                
                if shares > 0 and cash >= required_cash:
                    cash -= required_cash
                    open_positions[cand['symbol']] = {
                        "shares": shares,
                        "entry_date": current_date.strftime("%Y-%m-%d"),
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
    nifty_full = bulk_data.get("NIFTYBEES")
    regime_metrics = calculate_regime_metrics(trades_log, nifty_full)
    metrics.update(regime_metrics)
    return metrics, daily_equity_curve, trades_log



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
                        
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "pnl_pct": pnl, 
                            "status": "Loss"
                        })
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "pnl_pct": pnl, 
                            "status": "Win"
                        })
                        
        for sym in symbols_to_remove:
            del open_positions[sym]
            
        # 2. Evaluate new candidates (MOC execution at ~3:15 PM Close)
        new_candidates = []
        if cash > (INITIAL_CAPITAL * 0.05):
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
                    
                hist_df = df[df.index <= current_date]
                if len(hist_df) < 200:
                    continue
                    
                # Run eval for target strategies (Intersection)
                passed_strategies = []
                target_strategies = [s for s in strategies if s['name'] in ["Relative Strength", "Momentum Breakout"]]
                
                for strategy in target_strategies:
                    try:
                        sector_hist = None
                        if industry_mapping and sector_indices and sym in industry_mapping:
                            ind = industry_mapping[sym]
                            if ind in sector_indices:
                                sector_hist = sector_indices[ind][sector_indices[ind].index <= current_date]
                                
                        res = strategy['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist)
                        if res.get('passed', False):
                            passed_strategies.append(strategy)
                    except Exception as e:
                        pass
                
                # Check if AT LEAST ONE strategy passed (OR logic)
                if len(passed_strategies) >= 1:
                    strategy = passed_strategies[0]
                    close = hist_df['Close'].iloc[-1]
                    atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                    
                    if pd.notna(atr) and atr > 0:
                        new_candidates.append({
                            "symbol": sym,
                            "price": close,
                            "stop_loss": close - (atr * strategy['risk_atr']),
                            "target": close + (atr * strategy['reward_atr']),
                            "strategy_name": "RS OR Momentum (Union)"
                        })
                    
        # 3. Allocate Cash (MOC entry at Close price)
        if new_candidates:
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE
            
            for cand in new_candidates:
                risk_amount = total_equity * 0.02
                risk_per_share = cand['price'] - cand['stop_loss']
                
                if risk_per_share <= 0:
                    continue
                    
                ideal_shares = int(risk_amount / risk_per_share)
                max_shares = int(max_alloc_per_trade / cand['price'])
                shares = min(ideal_shares, max_shares)
                
                required_cash = shares * cand['price'] * (1 + FRICTION_PCT)
                
                if shares > 0 and cash >= required_cash:
                    cash -= required_cash
                    open_positions[cand['symbol']] = {
                        "shares": shares,
                        "entry_date": current_date.strftime("%Y-%m-%d"),
                        "entry_price": cand['price'],
                        "current_price": cand['price'],
                        "stop_loss": cand['stop_loss'],
                        "target": cand['target'],
                        "strategy": cand['strategy_name']
                    }
                        
        # 4. Record Daily Equity
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_equity_curve.append(total_equity)
        
    metrics = calculate_metrics(daily_equity_curve, trades_log, test_dates=test_dates)
    metrics["Strategy"] = "Ensemble (Intersection)"
    return metrics, daily_equity_curve, trades_log



def run_architectural_backtest(arch_config, test_dates, bulk_data, industry_mapping=None, sector_indices=None):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Backtesting Architecture: {arch_config['name']}...")
    
    ARCH_STARTING_CAPITAL = arch_config.get("starting_capital", INITIAL_CAPITAL)
    cash = ARCH_STARTING_CAPITAL
    FRICTION_PCT = arch_config.get("friction_pct", 0.0015)
    MAX_WEIGHT_PER_TRADE = 0.20
    open_positions = {}
    daily_equity_curve = []
    trades_log = []
    daily_exposure_log = []
    high_water_mark = cash
    hedge_position = None
    
    # Pre-calculate Breakout Continuation Rate (BCR) for regime-adaptive architectures
    bcr_series = {}
    breadth_series = {}  # % of stocks with Close > 50-day SMA — purely historical per day
    needs_regime = (
        arch_config.get("regime_adaptive") 
        or arch_config.get("enable_nifty_hedge") 
        or arch_config.get("block_on_bear_regime") 
        or arch_config.get("defensive_cash_preservation") 
        or arch_config.get("tighten_stops_on_bear") 
        or arch_config.get("dynamic_bear_risk_throttling")
    )
    if needs_regime:
        logger.info("  Pre-calculating BCR and Market Breadth...")
        
        # --- BCR: use breakouts from 120→30 days ago with 20-day outcomes (all past data) ---
        breakout_events = []
        for sym, df in bulk_data.items():
            if sym == "NIFTYBEES" or len(df) < 60:
                continue
            high_40 = df['High'].rolling(40).max().shift(1)
            for idx in range(40, len(df) - 20):
                if df['Close'].iloc[idx] > high_40.iloc[idx]:
                    entry_p = df['Close'].iloc[idx]
                    future_p = df['Close'].iloc[idx + 20]
                    breakout_events.append({
                        'date': df.index[idx],
                        'continued': 1 if future_p > entry_p else 0
                    })
        if breakout_events:
            ev_df = pd.DataFrame(breakout_events)
            ev_df['date'] = pd.to_datetime(ev_df['date'])
            for td in test_dates:
                td_ts = pd.Timestamp(td)
                win_start = td_ts - pd.Timedelta(days=120)
                win_end = td_ts - pd.Timedelta(days=30)
                window = ev_df[(ev_df['date'] >= win_start) & (ev_df['date'] <= win_end)]
                bcr_series[td_ts] = window['continued'].mean() if len(window) >= 10 else 0.5
        
        # --- Breadth: % stocks with Close > SMA50 on each day (purely historical) ---
        # Pre-compute each stock's Close > SMA50 as a boolean series
        above_sma_by_sym = {}
        for sym, df in bulk_data.items():
            if sym == "NIFTYBEES" or len(df) < 50:
                continue
            sma50 = df['Close'].rolling(50).mean()
            above_sma_by_sym[sym] = (df['Close'] > sma50)
        
        n_stocks = len(above_sma_by_sym)
        for td in test_dates:
            td_ts = pd.Timestamp(td)
            if n_stocks == 0:
                breadth_series[td_ts] = 0.5
                continue
            above = sum(
                1 for ab in above_sma_by_sym.values()
                if td_ts in ab.index and bool(ab.get(td_ts, False))
            )
            breadth_series[td_ts] = above / n_stocks
        
        logger.info(f"  BCR and Breadth calculated for {len(bcr_series)} days.")
    
    # Pre-calculate Top Sectors by Date if require_top_sectors is specified
    top_sectors_by_date = {}
    top_n = arch_config.get("require_top_sectors")
    if top_n and sector_indices and "NIFTYBEES" in bulk_data:
        logger.info(f"  Pre-calculating Top {top_n} Sectors per trading day...")
        nifty_close = bulk_data["NIFTYBEES"]['Close']
        for td in test_dates:
            td_ts = pd.Timestamp(td)
            sec_scores = []
            nifty_locs = nifty_close.index[nifty_close.index <= td_ts]
            if len(nifty_locs) >= 60:
                n_today = nifty_close.loc[nifty_locs[-1]]
                n_20 = nifty_close.loc[nifty_locs[-21]]
                n_60 = nifty_close.loc[nifty_locs[-61]]
                n_ret20 = (n_today / n_20) - 1.0
                n_ret60 = (n_today / n_60) - 1.0
                
                for sec_name, sec_df in sector_indices.items():
                    s_locs = sec_df.index[sec_df.index <= td_ts]
                    if len(s_locs) >= 60:
                        s_today = sec_df['Close'].loc[s_locs[-1]]
                        s_20 = sec_df['Close'].loc[s_locs[-21]]
                        s_60 = sec_df['Close'].loc[s_locs[-61]]
                        s_ret20 = (s_today / s_20) - 1.0
                        s_ret60 = (s_today / s_60) - 1.0
                        # Combined 20d and 60d relative strength score vs Nifty
                        score = (s_ret20 - n_ret20) + (s_ret60 - n_ret60)
                        sec_scores.append((sec_name, score))
                        
                sec_scores.sort(key=lambda x: x[1], reverse=True)
                top_sectors_by_date[td_ts] = set(x[0] for x in sec_scores[:top_n])
    
    for i, current_date in enumerate(test_dates):
        current_ts = pd.Timestamp(current_date)
        bcr_val = bcr_series.get(current_ts, 0.5)
        breadth_val = breadth_series.get(current_ts, 0.5)
        bear_bcr_threshold = arch_config.get("bear_bcr_threshold", 0.45)
        bear_breadth_threshold = arch_config.get("bear_breadth_threshold", 0.35)
        bear_regime = (bcr_val < bear_bcr_threshold) and (breadth_val < bear_breadth_threshold)
        
        n_curr = None
        if "NIFTYBEES" in bulk_data and current_date in bulk_data["NIFTYBEES"].index:
            n_row = bulk_data["NIFTYBEES"].loc[current_date]
            if isinstance(n_row, pd.DataFrame):
                n_row = n_row.iloc[-1]
            n_curr = float(n_row['Close'])
            
        # Bear stop compression if enabled
        if arch_config.get("tighten_stops_on_bear") and bear_regime:
            for p_pos in open_positions.values():
                p_atr = p_pos.get('atr', 0.0)
                if p_atr > 0:
                    tight_stop = p_pos['entry_price'] - (p_atr * 1.0)
                    p_pos['stop_loss'] = max(p_pos['stop_loss'], tight_stop)
                    p_pos['max_sessions'] = min(p_pos.get('max_sessions', MAX_HOLDING_SESSIONS), 7)
                    
        # 1. Update prices and check exits
        symbols_to_remove = []
        tm = arch_config.get("trade_management")
        for sym, pos in open_positions.items():
            if sym in bulk_data:
                df = bulk_data[sym]
                if current_date in df.index:
                    row = df.loc[current_date]
                    if isinstance(row, pd.DataFrame):
                        row = row.iloc[-1]
                        
                    high, low, close = row['High'], row['Low'], row['Close']
                    pos['current_price'] = close
                    pos_atr = pos.get('atr', 0.0)
                    
                    # 1A0. Defensive Cash Preservation in Bear Regime (cut loss immediately if below entry)
                    if arch_config.get("defensive_cash_preservation") and bear_regime and (close < pos['entry_price']):
                        exit_price = close
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "shares": pos["shares"],
                            "pnl_pct": pnl, 
                            "status": "BearCashPreserve"
                        })
                        continue
                        
                    # 1A. Stop Loss Hit (Evaluated BEFORE target to ensure conservative bias on intraday conflict)
                    if low <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        
                        status = "RunnerTrailStop" if pos.get("partial_scaled", False) else ("Win" if pnl > 0 else "Loss")
                        trades_log.append({
                            "symbol": sym, 
                            "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                            "entry_date": pos.get("entry_date", ""),
                            "exit_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": pos["entry_price"],
                            "exit_price": exit_price,
                            "stop_loss": pos["stop_loss"],
                            "target": pos["target"],
                            "shares": pos["shares"],
                            "pnl_pct": pnl, 
                            "status": status
                        })
                    # 1B. Target Hit
                    elif high >= pos['target']:
                        exit_price = pos['target']
                        
                        # Partial Scale Out: Sell 50% shares, let remainder trail with unconstrained target
                        if tm == "partial_scale_out" and not pos.get("partial_scaled", False) and pos["shares"] >= 2:
                            scaled_shares = pos["shares"] // 2
                            remaining_shares = pos["shares"] - scaled_shares
                            net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                            net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                            pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                            cash += scaled_shares * exit_price * (1 - FRICTION_PCT)
                            
                            trades_log.append({
                                "symbol": sym, 
                                "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                                "entry_date": pos.get("entry_date", ""),
                                "exit_date": current_date.strftime("%Y-%m-%d"),
                                "entry_price": pos["entry_price"],
                                "exit_price": exit_price,
                                "stop_loss": pos["stop_loss"],
                                "target": pos["target"],
                                "shares": scaled_shares,
                                "pnl_pct": pnl, 
                                "status": "PartialWin"
                            })
                            
                            pos["shares"] = remaining_shares
                            pos["partial_scaled"] = True
                            pos["target"] = pos["entry_price"] + (pos_atr * 10.0) # Uncap target for runner
                            be_stop = pos['entry_price'] * (1 + (FRICTION_PCT * 2))
                            pos['stop_loss'] = max(pos['stop_loss'], be_stop)     # Breakeven stop on runner
                            pos['max_sessions'] = 30                              # Extend time stop for runner
                            pos['highest_price'] = max(pos.get('highest_price', pos['entry_price']), high)
                            # sym is NOT added to symbols_to_remove so remaining shares ride
                        else:
                            net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                            net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                            pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                            cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                            symbols_to_remove.append(sym)
                            status = "RunnerTarget" if pos.get("partial_scaled", False) else "Win"
                            trades_log.append({
                                "symbol": sym, 
                                "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                                "entry_date": pos.get("entry_date", ""),
                                "exit_date": current_date.strftime("%Y-%m-%d"),
                                "entry_price": pos["entry_price"],
                                "exit_price": exit_price,
                                "stop_loss": pos["stop_loss"],
                                "target": pos["target"],
                                "shares": pos["shares"],
                                "pnl_pct": pnl, 
                                "status": status
                            })
                    # 1C. Position Survives Session: Check Time Stop, EMA20 Trail, Trailing Ratchet
                    else:
                        entry_dt = pd.Timestamp(pos.get("entry_date", current_date))
                        sessions_held = len([d for d in test_dates[:i+1] if d >= entry_dt]) - 1
                        max_sess = pos.get("max_sessions", MAX_HOLDING_SESSIONS)
                        
                        if sessions_held >= max_sess:
                            exit_price = close
                            net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                            net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                            pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                            cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                            symbols_to_remove.append(sym)
                            trades_log.append({
                                "symbol": sym, 
                                "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                                "entry_date": pos.get("entry_date", ""),
                                "exit_date": current_date.strftime("%Y-%m-%d"),
                                "entry_price": pos["entry_price"],
                                "exit_price": exit_price,
                                "stop_loss": pos["stop_loss"],
                                "target": pos["target"],
                                "shares": pos["shares"],
                                "pnl_pct": pnl, 
                                "status": "TimeStop"
                            })
                        else:
                            pos['highest_price'] = max(pos.get('highest_price', pos['entry_price']), high)
                            
                            ema20_triggered = False
                            if tm == "ema20_dynamic_trail" and pos_atr > 0:
                                if pos['highest_price'] >= pos['entry_price'] + (2.5 * pos_atr):
                                    stock_hist = df[df.index <= current_date]
                                    if len(stock_hist) >= 20:
                                        ema20_val = talib.EMA(stock_hist['Close'], timeperiod=20).iloc[-1]
                                        if pd.notna(ema20_val) and close < ema20_val:
                                            exit_price = close
                                            net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                                            net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                                            pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                                            cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                                            symbols_to_remove.append(sym)
                                            trades_log.append({
                                                "symbol": sym, 
                                                "signal_date": pos.get("signal_date", pos.get("entry_date", "")),
                                                "entry_date": pos.get("entry_date", ""),
                                                "exit_date": current_date.strftime("%Y-%m-%d"),
                                                "entry_price": pos["entry_price"],
                                                "exit_price": exit_price,
                                                "stop_loss": pos["stop_loss"],
                                                "target": pos["target"],
                                                "shares": pos["shares"],
                                                "pnl_pct": pnl, 
                                                "status": "EMA20Trail"
                                            })
                                            ema20_triggered = True
                            
                            if not ema20_triggered:
                                if tm == "breakeven_lock" and pos_atr > 0:
                                    if pos['highest_price'] >= pos['entry_price'] + (2.5 * pos_atr):
                                        be_stop = pos['entry_price'] * (1 + (FRICTION_PCT * 2))
                                        pos['stop_loss'] = max(pos['stop_loss'], be_stop)
                                elif tm == "partial_scale_out" and pos.get("partial_scaled", False) and pos_atr > 0:
                                    trail_stop = pos['highest_price'] - (2.5 * pos_atr)
                                    be_stop = pos['entry_price'] * (1 + (FRICTION_PCT * 2))
                                    pos['stop_loss'] = max(pos['stop_loss'], be_stop, trail_stop)
                                elif tm == "chandelier_runner" and pos_atr > 0:
                                    if pos['highest_price'] >= pos['entry_price'] + (2.0 * pos_atr):
                                        trail_stop = pos['highest_price'] - (2.5 * pos_atr)
                                        pos['stop_loss'] = max(pos['stop_loss'], trail_stop)
                                elif tm == "regime_adaptive_targets" and pos_atr > 0:
                                    if pos.get("tm_mode") == "regime_bull":
                                        if pos['highest_price'] >= pos['entry_price'] + (3.0 * pos_atr):
                                            be_stop = pos['entry_price'] * (1 + (FRICTION_PCT * 2))
                                            trail_stop = pos['highest_price'] - (2.0 * pos_atr)
                                            pos['stop_loss'] = max(pos['stop_loss'], be_stop, trail_stop)
                                elif arch_config.get("trailing_stop") == "breakeven_then_trail" and pos_atr > 0:
                                    if pos['highest_price'] >= pos['entry_price'] + (2.0 * pos_atr):
                                        be_stop = pos['entry_price'] * (1 + (FRICTION_PCT * 2))
                                        pos['stop_loss'] = max(pos['stop_loss'], be_stop)
                                    if pos['highest_price'] >= pos['entry_price'] + (3.0 * pos_atr):
                                        trail_stop = pos['highest_price'] - (1.5 * pos_atr)
                                        pos['stop_loss'] = max(pos['stop_loss'], trail_stop)
                        
        for sym in symbols_to_remove:
            del open_positions[sym]
            
        # 1D. Hedge Management (NIFTYBEES Inverse Short Hedge)
        if arch_config.get("enable_nifty_hedge") and n_curr is not None:
            unhedge_breadth = arch_config.get("unhedge_breadth_threshold", 0.40)
            unhedge_bcr = arch_config.get("unhedge_bcr_threshold", 0.50)
            
            # Check Unwind conditions for active hedge
            if hedge_position is not None:
                hedge_stop_hit = n_curr >= hedge_position['entry_price'] * 1.03  # 3% stop on hedge if market rallies
                market_recovered = (breadth_val >= unhedge_breadth) or (bcr_val >= unhedge_bcr)
                no_longs_left = (len(open_positions) == 0)
                is_final_date = (i == len(test_dates) - 1)
                
                if hedge_stop_hit or market_recovered or no_longs_left or is_final_date:
                    gross_cash = hedge_position['margin_cash'] + (hedge_position['entry_price'] - n_curr) * hedge_position['shares']
                    net_exit_cash = gross_cash - (n_curr * hedge_position['shares'] * FRICTION_PCT)
                    cash += net_exit_cash
                    h_pnl = (net_exit_cash - hedge_position['margin_cash']) / hedge_position['margin_cash'] if hedge_position['margin_cash'] > 0 else 0.0
                    trades_log.append({
                        "symbol": "NIFTYBEES_HEDGE",
                        "signal_date": hedge_position['entry_date'],
                        "entry_date": hedge_position['entry_date'],
                        "exit_date": current_date.strftime("%Y-%m-%d"),
                        "entry_price": hedge_position['entry_price'],
                        "exit_price": n_curr,
                        "stop_loss": hedge_position['entry_price'] * 1.03,
                        "target": 0.0,
                        "shares": hedge_position['shares'],
                        "pnl_pct": h_pnl,
                        "status": "HedgeStop" if hedge_stop_hit else ("HedgeCover" if market_recovered else "HedgeUnwind")
                    })
                    hedge_position = None
            
            # Check Entry condition for new hedge
            if hedge_position is None and bear_regime and len(open_positions) > 0 and i < len(test_dates) - 1:
                long_val = sum(p['shares'] * p['current_price'] for p in open_positions.values())
                hedge_ratio = arch_config.get("hedge_ratio", 0.50)
                target_hedge_val = long_val * hedge_ratio
                ideal_h_shares = int(target_hedge_val / n_curr)
                if ideal_h_shares > 0:
                    margin_cap = cash * 0.90  # Keep 10% cash buffer
                    actual_h_shares = min(ideal_h_shares, int(margin_cap / n_curr)) if margin_cap > 0 else 0
                    if actual_h_shares > 0:
                        margin_cash = actual_h_shares * n_curr
                        friction_cost = margin_cash * FRICTION_PCT
                        if cash >= (margin_cash + friction_cost):
                            cash -= (margin_cash + friction_cost)
                            hedge_position = {
                                "shares": actual_h_shares,
                                "entry_price": n_curr,
                                "margin_cash": margin_cash,
                                "entry_date": current_date.strftime("%Y-%m-%d")
                            }

        hedge_equity = 0.0
        if hedge_position is not None and n_curr is not None:
            hedge_equity = hedge_position['margin_cash'] + (hedge_position['entry_price'] - n_curr) * hedge_position['shares']
            
        current_equity_for_hwm = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values()) + hedge_equity
        if current_equity_for_hwm > high_water_mark:
            high_water_mark = current_equity_for_hwm
            
        risk_multiplier = 1.0
        max_weight_multiplier = 1.0
        if arch_config.get("dynamic_risk_scaling"):
            current_drawdown = (current_equity_for_hwm - high_water_mark) / high_water_mark
            if current_drawdown < -0.05:
                penalty = (abs(current_drawdown) - 0.05) * 5.0
                risk_multiplier = max(0.20, 1.0 - penalty)
                
        if arch_config.get("dynamic_bear_risk_throttling") and (bcr_val < 0.48 or breadth_val < 0.40):
            risk_multiplier = min(risk_multiplier, 0.35)
            max_weight_multiplier = 0.35
            
        # 2. Evaluate new candidates
        new_candidates = []
        if cash > (ARCH_STARTING_CAPITAL * 0.05):
            nifty_hist = None
            if "NIFTYBEES" in bulk_data and current_date in bulk_data["NIFTYBEES"].index:
                nifty_hist = bulk_data["NIFTYBEES"][bulk_data["NIFTYBEES"].index <= current_date]
                
            # Regime filter check
            market_regime_blocked = False
            if arch_config.get("block_on_bearish_regime") and nifty_hist is not None and len(nifty_hist) > 200:
                n_close = nifty_hist['Close'].iloc[-1]
                n_sma200 = nifty_hist['Close'].rolling(200).mean().iloc[-1]
                if n_close < n_sma200:
                    market_regime_blocked = True
                    
            if arch_config.get("block_on_bear_regime") and bear_regime:
                market_regime_blocked = True
                    
            if not market_regime_blocked:
                for sym, df in bulk_data.items():
                    if sym == "NIFTYBEES":
                        continue
                    if sym in open_positions:
                        continue
                        
                    # Top Sectors Filter (Focus on Leading Institutional Flows)
                    if top_n and industry_mapping:
                        allowed_secs = top_sectors_by_date.get(pd.Timestamp(current_date), set())
                        stock_sec = industry_mapping.get(sym)
                        if not stock_sec or stock_sec not in allowed_secs:
                            continue
                        
                    hist_df = df[df.index <= current_date]
                    if len(hist_df) < 200:
                        continue
                        
                    sector_hist = None
                    if industry_mapping and sector_indices and sym in industry_mapping:
                        ind = industry_mapping[sym]
                        if ind in sector_indices:
                            sector_hist = sector_indices[ind][sector_indices[ind].index <= current_date]
                    
                    # Core Eval — Three-State Regime-Adaptive or Standard
                    if arch_config.get("regime_adaptive"):
                        bcr_val = bcr_series.get(pd.Timestamp(current_date), 0.5)
                        bcr_threshold = arch_config.get("bcr_threshold", 0.52)
                        breadth_val = breadth_series.get(pd.Timestamp(current_date), 0.5)
                        breadth_threshold = arch_config.get("breadth_threshold", 0.30)
                        
                        if bcr_val > bcr_threshold:
                            # STATE 1 — TREND: BCR above coin flip → momentum signals
                            primary = arch_config.get('primary_momentum', arch_config['primary'])
                            confirmation = arch_config.get('confirmation_momentum', arch_config.get('confirmation'))
                        elif arch_config.get("cash_preservation") and breadth_val < breadth_threshold:
                            # STATE 3 — CASH PRESERVATION: BCR weak AND breadth extremely weak
                            # Skip this stock entirely — no new positions in this environment.
                            # (Existing positions still managed via stops/targets above.)
                            # FORWARD-BIAS NOTE: breadth_val uses Close > SMA50 on the CURRENT day
                            # — purely historical, no look-ahead.
                            continue
                        else:
                            # STATE 2 — MEAN-REVERSION: BCR weak but breadth not extreme
                            primary = arch_config.get('primary_meanrev', arch_config['primary'])
                            confirmation = arch_config.get('confirmation_meanrev', arch_config.get('confirmation'))
                    else:
                        primary = arch_config['primary']
                        confirmation = arch_config.get('confirmation')
                    
                    try:
                        p_res = primary['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist)
                    except: p_res = {}
                    
                    try:
                        c_res = confirmation['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist) if confirmation else None
                    except: c_res = None
                    
                    filter_strat = arch_config.get('filter')
                    try:
                        f_res = filter_strat['func'](hist_df, nifty_hist=nifty_hist, sector_hist=sector_hist) if filter_strat else None
                    except: f_res = None
                    
                    # Relative Strength (RS) & Mansfield Filters (Option 2)
                    rs_score = 0.0
                    if p_res and p_res.get('passed'):
                        mrs_filter = arch_config.get("mrs_filter", False)
                        if mrs_filter and nifty_hist is not None and len(nifty_hist) >= 60 and len(hist_df) >= 60:
                            common_idx = hist_df.index.intersection(nifty_hist.index)[-60:]
                            if len(common_idx) >= 50:
                                s_c = hist_df['Close'].loc[common_idx]
                                n_c = nifty_hist['Close'].loc[common_idx]
                                rs_series = s_c / n_c
                                rs_sma50 = rs_series.rolling(50).mean().iloc[-1]
                                if pd.isna(rs_sma50) or rs_series.iloc[-1] <= rs_sma50:
                                    continue  # Fails Mansfield RS > 0 (trading below 50d RS SMA)
                            else:
                                continue
                                
                        dual_rs_filter = arch_config.get("dual_rs_filter", False)
                        if dual_rs_filter and nifty_hist is not None and len(nifty_hist) >= 61 and len(hist_df) >= 61:
                            s_ret20 = (hist_df['Close'].iloc[-1] / hist_df['Close'].iloc[-21]) - 1.0
                            n_ret20 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-21]) - 1.0
                            s_ret60 = (hist_df['Close'].iloc[-1] / hist_df['Close'].iloc[-61]) - 1.0
                            n_ret60 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-61]) - 1.0
                            if (s_ret20 <= n_ret20) or (s_ret60 <= n_ret60):
                                continue  # Fails Dual-Period Outperformance (must beat Nifty on both 20d and 60d)
                                
                        min_rs_outperformance = arch_config.get("min_rs_outperformance")
                        if nifty_hist is not None and len(nifty_hist) >= 61 and len(hist_df) >= 61:
                            s_ret60 = (hist_df['Close'].iloc[-1] / hist_df['Close'].iloc[-61]) - 1.0
                            n_ret60 = (nifty_hist['Close'].iloc[-1] / nifty_hist['Close'].iloc[-61]) - 1.0
                            rs_score = s_ret60 - n_ret60
                            if min_rs_outperformance is not None and rs_score < min_rs_outperformance:
                                continue  # Fails minimum 60d relative alpha threshold
                    
                    # Architecture Logic
                    sizing_logic = arch_config.get('sizing_logic', 'primary_only')
                    risk_pct = 0.0
                    is_confirmed = False
                    
                    if sizing_logic == "primary_only":
                        if p_res and p_res.get('passed'): risk_pct = 0.02
                    elif sizing_logic == "union":
                        if (p_res and p_res.get('passed')) or (c_res and c_res.get('passed')): risk_pct = 0.02
                    elif sizing_logic == "voting":
                        score = 0
                        if p_res and p_res.get('passed'): score += 1
                        if c_res and c_res.get('passed'): score += 1
                        if score == 1: risk_pct = 0.01
                        elif score == 2: risk_pct = 0.02
                    elif sizing_logic == "alpha_confirmation":
                        is_confirmed = False
                        if p_res and p_res.get('passed'):
                            if c_res and c_res.get('passed'):
                                risk_pct = RISK_CONFIRMED
                                is_confirmed = True
                            else:
                                risk_pct = RISK_PRIMARY
                    elif sizing_logic == "momentum_risk_filter":
                        if p_res and p_res.get('passed'):
                            if c_res and c_res.get('passed'): risk_pct = 0.02
                            else: risk_pct = 0.00
                    elif sizing_logic == "volatility_filter":
                        if p_res and p_res.get('passed'):
                            if f_res and f_res.get('passed'): risk_pct = 0.03
                            else: risk_pct = 0.015
                    elif sizing_logic == "volatility_scaled":
                        if p_res and p_res.get('passed'):
                            base_risk = 0.025 if (c_res and c_res.get('passed')) else 0.01
                            
                            close = hist_df['Close'].iloc[-1]
                            atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                            if pd.notna(atr) and atr > 0:
                                current_atr_pct = atr / close
                                baseline_atr_pct = 0.05 # Assume 5% is normal daily volatility
                                
                                # Scale risk inversely with volatility
                                vol_scalar = baseline_atr_pct / current_atr_pct
                                
                                # Cap the scalar so we don't take crazy sizes on low vol, and don't reduce to zero on high vol
                                vol_scalar = max(0.5, min(vol_scalar, 2.0))
                                
                                risk_pct = base_risk * vol_scalar
                    
                    if risk_pct > 0:
                        risk_pct = risk_pct * risk_multiplier
                        # Canonical E12 uses a near-close/MOC entry.  The live
                        # screener records its 3:15 price; this historical proxy
                        # uses that day's close and must be interpreted as such.
                        entry_price = hist_df['Close'].iloc[-1]
                        atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                        if pd.notna(atr) and atr > 0:
                            risk_atr = arch_config.get("risk_atr", RISK_ATR)
                            reward_atr = arch_config.get("reward_atr", REWARD_ATR)
                            max_sessions = MAX_HOLDING_SESSIONS
                            tm_mode = ""
                            
                            tm = arch_config.get("trade_management")
                            if tm == "chandelier_runner":
                                reward_atr = arch_config.get("reward_atr", 10.0)
                                max_sessions = 25
                            elif tm == "regime_adaptive_targets":
                                bcr_val = bcr_series.get(pd.Timestamp(current_date), 0.5)
                                if bcr_val > 0.65:
                                    reward_atr = 6.0
                                    risk_atr = 2.0
                                    max_sessions = 20
                                    tm_mode = "regime_bull"
                                else:
                                    reward_atr = 3.5
                                    risk_atr = 2.0
                                    max_sessions = 12
                                    tm_mode = "regime_chop"
                            elif tm == "ema20_dynamic_trail":
                                reward_atr = arch_config.get("reward_atr", 6.0)
                                risk_atr = arch_config.get("risk_atr", 2.0)
                                max_sessions = 25
                            
                            # A2+A3: Adaptive Risk/Reward based on confirmation
                            if arch_config.get("adaptive_rr") and sizing_logic == "alpha_confirmation":
                                if is_confirmed:
                                    risk_atr = 1.5    # Tighter stop on high conviction
                                    reward_atr = 5.0   # Let right tail run
                                else:
                                    risk_atr = 2.5    # Wider stop on lower conviction
                                    reward_atr = 4.0   # Standard target
                            elif arch_config.get("adaptive_target_expansion"):
                                if is_confirmed:
                                    risk_atr = arch_config.get("confirmed_risk_atr", 2.0)
                                    reward_atr = arch_config.get("confirmed_reward_atr", 5.0)
                                else:
                                    risk_atr = arch_config.get("primary_risk_atr", 2.0)
                                    reward_atr = arch_config.get("primary_reward_atr", 4.0)
                            
                            alpha_score = p_res.get('alpha_score', 0.0) if p_res else 0.0
                            new_candidates.append({
                                "symbol": sym,
                                "price": entry_price,
                                "entry_date": current_date.strftime("%Y-%m-%d"),
                                "signal_date": current_date.strftime("%Y-%m-%d"),
                                "stop_loss": entry_price - (atr * risk_atr),
                                "target": entry_price + (atr * reward_atr),
                                "atr": atr,
                                "risk_pct": risk_pct,
                                "alpha_score": alpha_score,
                                "confirmed": is_confirmed,
                                "max_sessions": max_sessions,
                                "tm_mode": tm_mode,
                                "rs_score": rs_score,
                            })
                            
        # Allocate cash
        if new_candidates:
            # Rank candidates by RS score or alpha score (best first)
            if arch_config.get("rank_by_rs"):
                confirmed = sorted((c for c in new_candidates if c["confirmed"]), key=lambda c: (c.get("rs_score", 0.0), c["alpha_score"]), reverse=True)
                primary = sorted((c for c in new_candidates if not c["confirmed"]), key=lambda c: (c.get("rs_score", 0.0), c["alpha_score"]), reverse=True)
                new_candidates = confirmed[:MAX_CONFIRMED_SIGNALS] + primary[:MAX_PRIMARY_SIGNALS]
            elif arch_config.get("rank_candidates"):
                confirmed = sorted((c for c in new_candidates if c["confirmed"]), key=lambda c: c["alpha_score"], reverse=True)
                primary = sorted((c for c in new_candidates if not c["confirmed"]), key=lambda c: c["alpha_score"], reverse=True)
                new_candidates = confirmed[:MAX_CONFIRMED_SIGNALS] + primary[:MAX_PRIMARY_SIGNALS]
            
            hedge_equity = 0.0
            if hedge_position is not None and n_curr is not None:
                hedge_equity = hedge_position['margin_cash'] + (hedge_position['entry_price'] - n_curr) * hedge_position['shares']
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values()) + hedge_equity
            max_alloc_per_trade = total_equity * (MAX_WEIGHT_PER_TRADE * max_weight_multiplier) * risk_multiplier
            max_per_sector = arch_config.get("max_positions_per_sector")
            
            if "portfolio_cap" in arch_config:
                portfolio_cap = arch_config.get("portfolio_cap", 1.0)
                max_total_allocation = total_equity * portfolio_cap
                current_invested = sum(p['shares'] * p['current_price'] for p in open_positions.values())
                available_allocation = max_total_allocation - current_invested
                
                ideal_allocations = []
                for cand in new_candidates:
                    if max_per_sector and industry_mapping:
                        cand_sec = industry_mapping.get(cand['symbol'])
                        if cand_sec:
                            curr_sec_count = sum(1 for p_sym in open_positions if industry_mapping.get(p_sym) == cand_sec)
                            if curr_sec_count >= max_per_sector:
                                continue
                    risk_amount = total_equity * cand['risk_pct']
                    risk_per_share = cand['price'] - cand['stop_loss']
                    if risk_per_share <= 0: continue
                    ideal_shares = int(risk_amount / risk_per_share)
                    max_shares = int(max_alloc_per_trade / cand['price'])
                    shares = min(ideal_shares, max_shares)
                    ideal_allocations.append({
                        'cand': cand,
                        'ideal_shares': shares,
                        'cost': shares * cand['price']
                    })
                    
                total_ideal_cost = sum(x['cost'] for x in ideal_allocations)
                
                scaling_factor = 1.0
                if total_ideal_cost > available_allocation and available_allocation > 0:
                    scaling_factor = available_allocation / total_ideal_cost
                elif available_allocation <= 0:
                    scaling_factor = 0.0
                    
                for alloc in ideal_allocations:
                    cand = alloc['cand']
                    if max_per_sector and industry_mapping:
                        cand_sec = industry_mapping.get(cand['symbol'])
                        if cand_sec:
                            curr_sec_count = sum(1 for p_sym in open_positions if industry_mapping.get(p_sym) == cand_sec)
                            if curr_sec_count >= max_per_sector:
                                continue
                    final_shares = int(alloc['ideal_shares'] * scaling_factor)
                    required_cash = final_shares * cand['price'] * (1 + FRICTION_PCT)
                    
                    if final_shares > 0 and cash >= required_cash:
                        cash -= required_cash
                        open_positions[cand['symbol']] = {
                            "shares": final_shares,
                            "entry_date": cand["entry_date"],
                            "signal_date": cand["signal_date"],
                            "entry_price": cand['price'],
                            "current_price": cand['price'],
                            "highest_price": cand['price'],
                            "stop_loss": cand['stop_loss'],
                            "target": cand['target'],
                            "atr": cand.get('atr', 0.0),
                            "max_sessions": cand.get('max_sessions', MAX_HOLDING_SESSIONS),
                            "tm_mode": cand.get('tm_mode', ''),
                            "partial_scaled": False,
                        }
            else:
                for cand in new_candidates:
                    if max_per_sector and industry_mapping:
                        cand_sec = industry_mapping.get(cand['symbol'])
                        if cand_sec:
                            curr_sec_count = sum(1 for p_sym in open_positions if industry_mapping.get(p_sym) == cand_sec)
                            if curr_sec_count >= max_per_sector:
                                continue
                    risk_amount = total_equity * cand['risk_pct']
                    risk_per_share = cand['price'] - cand['stop_loss']
                    if risk_per_share <= 0: continue
                    ideal_shares = int(risk_amount / risk_per_share)
                    max_shares = int(max_alloc_per_trade / cand['price'])
                    shares = min(ideal_shares, max_shares)
                    required_cash = shares * cand['price'] * (1 + FRICTION_PCT)
                    
                    if shares > 0 and cash >= required_cash:
                        cash -= required_cash
                        open_positions[cand['symbol']] = {
                            "shares": shares,
                            "entry_date": cand["entry_date"],
                            "signal_date": cand["signal_date"],
                            "entry_price": cand['price'],
                            "current_price": cand['price'],
                            "highest_price": cand['price'],
                            "stop_loss": cand['stop_loss'],
                            "target": cand['target'],
                            "atr": cand.get('atr', 0.0),
                            "max_sessions": cand.get('max_sessions', MAX_HOLDING_SESSIONS),
                            "tm_mode": cand.get('tm_mode', ''),
                            "partial_scaled": False,
                        }
                    
        hedge_equity = 0.0
        if hedge_position is not None and n_curr is not None:
            hedge_equity = hedge_position['margin_cash'] + (hedge_position['entry_price'] - n_curr) * hedge_position['shares']
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values()) + hedge_equity
        daily_equity_curve.append(total_equity)
        
        invested = sum(p['shares'] * p['current_price'] for p in open_positions.values())
        hedge_val = hedge_position['shares'] * n_curr if hedge_position and n_curr else 0.0
        daily_exposure_log.append({
            "Date": current_date.strftime("%Y-%m-%d"),
            "Total_Equity": total_equity,
            "Invested": invested,
            "Hedge_Value": hedge_val,
            "Exposure_Pct": invested / total_equity if total_equity > 0 else 0,
            "Num_Positions": len(open_positions),
            "Risk_Multiplier": risk_multiplier,
            "Bear_Regime": int(bear_regime)
        })
        
    # Terminal unwind for any active hedge
    if hedge_position is not None:
        last_date = test_dates[-1]
        n_last = hedge_position['entry_price']
        if "NIFTYBEES" in bulk_data and last_date in bulk_data["NIFTYBEES"].index:
            n_row = bulk_data["NIFTYBEES"].loc[last_date]
            if isinstance(n_row, pd.DataFrame):
                n_row = n_row.iloc[-1]
            n_last = float(n_row['Close'])
            
        gross_cash = hedge_position['margin_cash'] + (hedge_position['entry_price'] - n_last) * hedge_position['shares']
        net_exit_cash = gross_cash - (n_last * hedge_position['shares'] * FRICTION_PCT)
        cash += net_exit_cash
        h_pnl = (net_exit_cash - hedge_position['margin_cash']) / hedge_position['margin_cash'] if hedge_position['margin_cash'] > 0 else 0.0
        trades_log.append({
            "symbol": "NIFTYBEES_HEDGE",
            "signal_date": hedge_position['entry_date'],
            "entry_date": hedge_position['entry_date'],
            "exit_date": last_date.strftime("%Y-%m-%d"),
            "entry_price": hedge_position['entry_price'],
            "exit_price": n_last,
            "stop_loss": 0.0,
            "target": 0.0,
            "shares": hedge_position['shares'],
            "pnl_pct": h_pnl,
            "status": "HedgeFinalUnwind"
        })
        hedge_position = None
        
    metrics = calculate_metrics(daily_equity_curve, trades_log, test_dates=test_dates)
    metrics["Strategy"] = arch_config["name"]
    
    # Save daily exposure log
    safe_name = arch_config['name'].replace(' ', '_').replace(':', '')
    out_dir = "/Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing"
    os.makedirs(out_dir, exist_ok=True)
    pd.DataFrame(daily_exposure_log).to_csv(f"{out_dir}/{safe_name}_exposure.csv", index=False)
    
    # Calculate Regime Breakdown
    nifty_full = bulk_data.get("NIFTYBEES")
    regime_metrics = calculate_regime_metrics(trades_log, nifty_full)
    metrics.update(regime_metrics)
    
    return metrics, daily_equity_curve, trades_log


def main():
    from datetime import datetime, timedelta
    # Keep this full history for context, but judge the frozen strategy primarily
    # on validation_report.csv's post-2024-08-25 holdout period. Do not retune
    # parameters after inspecting that holdout.
    years_to_test = 6
    today = date.today()
    calendar_days_since_start = years_to_test * 365
    start_date = today - timedelta(days=calendar_days_since_start)
    # Need 300 trading days of history before start for indicator warmup (SMA200 etc.)
    # 300 trading days is roughly 434 calendar days (300 * 365 / 252). We use 450 to be safe.
    total_lookback = calendar_days_since_start + 450
    
    logger.info(f"Loading NIFTY 500 universe...")
    universe = load_nifty500_symbols()
    if "NIFTYBEES" not in universe:
        universe.append("NIFTYBEES")
    
    logger.info(f"Fetching bulk history for last {total_lookback} days...")
    bulk_data = fetch_bulk_history(universe, date.today(), lookback_days=total_lookback)
    
    # Align dates using NIFTYBEES as the source of truth for trading days
    if "NIFTYBEES" not in bulk_data:
        logger.error("NIFTYBEES missing from bulk data. Cannot align dates.")
        return
        
    nifty_all_dates = sorted(bulk_data["NIFTYBEES"].index)
    test_dates = [d for d in nifty_all_dates if d.date() >= start_date]
    logger.info(f"Backtesting over {len(test_dates)} trading days (from {test_dates[0].date()} to {test_dates[-1].date()})...")
    
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

    # Define strategy components
    vol_strat = {"name": "Volatility Compression", "func": volatility_compression_eval, "risk_atr": 1.0, "reward_atr": 3.0}
    oversold_strat = {"name": "Oversold Uptrend", "func": oversold_uptrend_eval, "risk_atr": 2.0, "reward_atr": 4.0}
    pullback_strat = {"name": "Trend Pullback", "func": trend_pullback_eval, "risk_atr": 2.0, "reward_atr": 4.0}
    sector_strat = {"name": "Sector Relative Pullback", "func": sector_pullback_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    connors_strat = {"name": "Connors RSI-2 Dip", "func": connors_rsi_eval, "risk_atr": 1.5, "reward_atr": 3.0}
    avwap_strat = {"name": "AVWAP Pullback", "func": avwap_pullback_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    dual_avwap_strat = {"name": "Dual AVWAP Confluence", "func": dual_avwap_pullback_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    vol_surge_strat = {"name": "Volume Surge AVWAP", "func": volume_surge_avwap_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    dual_avwap_vol_strat = {"name": "Alpha Max Dual AVWAP", "func": dual_avwap_volume_surge_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    leader_strat = {"name": "Leader Consolidation", "func": leader_consolidation_eval, "risk_atr": 1.5, "reward_atr": 4.0}
    thrust_strat = {"name": "Breadth Thrust Reversal", "func": breadth_thrust_eval, "risk_atr": 1.5, "reward_atr": 3.5}
    
    ARCHITECTURES = [
        {
            "name": "E19_Baseline",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        },
        {
            "name": "E19_H1_Cash_Preservation_Strict",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "block_on_bear_regime": True,
            "defensive_cash_preservation": True,
            "bear_bcr_threshold": 0.45,
            "bear_breadth_threshold": 0.35,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        },
        {
            "name": "E19_H2_Nifty_Inverse_Hedge",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "block_on_bear_regime": True,
            "enable_nifty_hedge": True,
            "hedge_ratio": 0.50,
            "bear_bcr_threshold": 0.45,
            "bear_breadth_threshold": 0.35,
            "unhedge_breadth_threshold": 0.40,
            "unhedge_bcr_threshold": 0.50,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        },
        {
            "name": "E19_H3_Dynamic_Risk_Throttling",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "block_on_bear_regime": True,
            "dynamic_bear_risk_throttling": True,
            "bear_bcr_threshold": 0.45,
            "bear_breadth_threshold": 0.35,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        },
        {
            "name": "E19_H4_Tightened_Stops_Bear",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "block_on_bear_regime": True,
            "tighten_stops_on_bear": True,
            "bear_bcr_threshold": 0.45,
            "bear_breadth_threshold": 0.35,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        },
        {
            "name": "E19_H5_Full_Regime_Shield",
            "primary": dual_avwap_strat,
            "primary_momentum": dual_avwap_strat,
            "confirmation_momentum": vol_strat,
            "primary_meanrev": pullback_strat,
            "confirmation_meanrev": connors_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": False,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": BCR_THRESHOLD,
            "cash_preservation": True,
            "breadth_threshold": BREADTH_THRESHOLD,
            "block_on_bear_regime": True,
            "defensive_cash_preservation": True,
            "enable_nifty_hedge": True,
            "hedge_ratio": 0.50,
            "tighten_stops_on_bear": True,
            "bear_bcr_threshold": 0.45,
            "bear_breadth_threshold": 0.35,
            "unhedge_breadth_threshold": 0.40,
            "unhedge_bcr_threshold": 0.50,
            "risk_atr": 2.0,
            "reward_atr": 4.0
        }
    ]
    
    tear_sheet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing", "strategy_tear_sheet.csv")
    os.makedirs(os.path.dirname(tear_sheet_path), exist_ok=True)
    
    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    tasks = []
    for s in STRATEGIES:
        tasks.append({"name": s["name"], "func": run_strategy_backtest, "arg": s})
    for a in ARCHITECTURES:
        tasks.append({"name": a["name"], "func": run_architectural_backtest, "arg": a})
        
    logger.info(f"Starting parallel backtest experiments for {len(tasks)} strategies using ProcessPoolExecutor...")
    
    futures = {}
    with ProcessPoolExecutor(max_workers=min(len(tasks), 8)) as executor:
        for t in tasks:
            future = executor.submit(
                t["func"], 
                t["arg"], 
                test_dates, 
                bulk_data, 
                industry_mapping, 
                sector_indices
            )
            futures[future] = t
            
        for future in as_completed(futures):
            t = futures[future]
            try:
                metrics, curve, trades = future.result()
                results.append(metrics)
                curves[t['name']] = curve
                
                # Save trades log
                if trades:
                    trades_df = pd.DataFrame(trades)
                    safe_name = t['name'].replace(" ", "_").replace(":", "")
                    trades_csv_path = os.path.join(os.path.dirname(tear_sheet_path), f"{safe_name}_backtest_trades.csv")
                    trades_df.to_csv(trades_csv_path, index=False)
            except Exception as e:
                logger.error(f"Error backtesting {t['name']}: {e}")
                import traceback
                traceback.print_exc()

    results_df = pd.DataFrame(results)
    results_df = results_df.set_index("Strategy")
    results_df = results_df.sort_values(by="Sharpe Ratio", ascending=False)
    
    tear_sheet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing", "strategy_tear_sheet.csv")
    results_df.to_csv(tear_sheet_path)
    
    curves_df = pd.DataFrame(curves, index=test_dates)
    curves_path = os.path.join(os.path.dirname(tear_sheet_path), "strategy_equity_curves.csv")
    curves_df.to_csv(curves_path)

    # Write a separate validation report.  The holdout starts after the model
    # design period and must not be used for parameter selection.
    validation_rows = []
    for strategy_name, curve in curves.items():
        in_sample = summarize_equity_period(
            strategy_name, curve, test_dates, "In-sample (frozen design)", test_dates[0], HOLDOUT_START
        )
        holdout = summarize_equity_period(
            strategy_name, curve, test_dates, "Holdout (no retuning)", HOLDOUT_START
        )
        if in_sample:
            validation_rows.append(in_sample)
        if holdout:
            validation_rows.append(holdout)
    validation_path = os.path.join(os.path.dirname(tear_sheet_path), "validation_report.csv")
    pd.DataFrame(validation_rows).to_csv(validation_path, index=False)

    # Save Monthly Returns Breakdown Matrix
    monthly_data = {}
    for strat_name, curve in curves.items():
        s = pd.Series(curve, index=pd.to_datetime(test_dates))
        try:
            m = s.resample('ME').last()
        except Exception:
            m = s.resample('M').last()
        monthly_data[strat_name] = (m.pct_change() * 100).round(2)
    
    if monthly_data:
        monthly_df = pd.DataFrame(monthly_data)
        monthly_matrix_path = os.path.join(os.path.dirname(tear_sheet_path), "monthly_returns_breakdown.csv")
        monthly_df.to_csv(monthly_matrix_path)
        logger.info(f"Monthly returns matrix saved to {monthly_matrix_path}")

    def serializable_architecture(architecture):
        return {
            key: (value["name"] if isinstance(value, dict) and "name" in value else value)
            for key, value in architecture.items()
            if key != "func"
        }

    run_config = {
        "run_date": today.isoformat(),
        "test_start": test_dates[0].date().isoformat(),
        "test_end": test_dates[-1].date().isoformat(),
        "holdout_start": HOLDOUT_START.date().isoformat(),
        "universe": "Current NIFTY 500 constituents plus NIFTYBEES benchmark",
        "universe_limitation": "Not point-in-time constituents; obtain a historical constituent dataset before treating results as survivorship-bias-free.",
        "execution": "Signal at 3:15 PM; near-close/MOC fill proxied by the daily close in historical data",
        "transaction_cost_per_leg": FRICTION_PCT,
        "position_cap": MAX_WEIGHT_PER_TRADE,
        "starting_capital": INITIAL_CAPITAL,
        "data_integrity": "Weekends rejected; exchange holidays excluded when no valid bhavcopy is available",
        "architectures": [serializable_architecture(architecture) for architecture in ARCHITECTURES],
    }
    config_payload = json.dumps(run_config, sort_keys=True, indent=2)
    run_config["config_sha256"] = hashlib.sha256(config_payload.encode("utf-8")).hexdigest()
    config_path = os.path.join(os.path.dirname(tear_sheet_path), "backtest_run_config.json")
    with open(config_path, "w") as config_file:
        json.dump(run_config, config_file, indent=2)
    
    # Append to experiment log
    from datetime import datetime
    experiment_log_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))), "experiment_log.csv")
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
    logger.info(f"Validation report saved to {validation_path}")
    logger.info(f"Reproducible run configuration saved to {config_path}")
    logger.info(f"Appended results to {experiment_log_path}")
    years = round(calendar_days_since_start / 365, 1)
    print(f"\n================= STRATEGY TEAR SHEET (LAST {years} YEARS) =================")
    print(results_df.to_string())
    print("======================================================================\n")

if __name__ == "__main__":
    main()
