import os
import sys
import logging
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
    relative_strength_eval
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

INITIAL_CAPITAL = 5_00_000.0  #   This does NOT affect architectural backtests (E4/A1/E11 etc).
                              # Architectural backtests use a hardcoded 5L in run_architectural_backtest().
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
    
    # Trades & Trade-Level Diagnostics
    wins = [t for t in trades if t['pnl_pct'] > 0]
    losses = [t for t in trades if t['pnl_pct'] <= 0]
    win_rate = (len(wins) / len(trades) * 100) if trades else 0
    overall_profit = equity_series.iloc[-1] - INITIAL_CAPITAL
    
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
    
    gross_win = sum([t['pnl_pct'] for t in wins]) if wins else 0
    gross_loss = abs(sum([t['pnl_pct'] for t in losses])) if losses else 0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (99 if gross_win > 0 else 0)
    
    expectancy = (win_rate/100 * avg_win) - ((1 - win_rate/100) * abs(avg_loss))
    
    # Calculate Turnover (total entry value / initial capital)
    turnover = sum([t['entry_price'] * t.get('shares', 1) for t in trades]) / INITIAL_CAPITAL
    
    # Calculate Avg Exposure
    # We estimate exposure as (1 - cash/equity) averaged over the curve, but we only have total equity in daily_equity.
    # We can pass daily_cash in the future, or approximate it here. Let's return N/A for now and compute properly later if needed.
    
    return {
        "Overall Profit (Rs)": round(overall_profit, 2),
        "CAGR (%)": round(cagr, 2),
        "Max Drawdown (%)": round(mdd, 2),
        "Win Rate (%)": round(win_rate, 2),
        "Sharpe Ratio": round(sharpe, 3),
        "Sortino Ratio": round(sortino, 3),
        "Calmar Ratio": round(calmar, 3),
        "Total Trades": len(trades),
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
                                "target": close + (atr * strategy['reward_atr'])
                            })
                except Exception as e:
                    pass # Skip if eval fails
                    
        # 3. Allocate Cash (MOC entry at Close price)
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
        
    metrics = calculate_metrics(daily_equity_curve, trades_log)
    metrics["Strategy"] = "Ensemble (Intersection)"
    return metrics, daily_equity_curve, trades_log



def run_architectural_backtest(arch_config, test_dates, bulk_data, industry_mapping=None, sector_indices=None):
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Backtesting Architecture: {arch_config['name']}...")
    
    # ⚠️ ARCHITECTURAL BACKTEST ALWAYS STARTS WITH 5L — INDEPENDENT OF INITIAL_CAPITAL CONSTANT ABOVE
    # Changing INITIAL_CAPITAL at the top of the file has NO effect here.
    ARCH_STARTING_CAPITAL = 5_00_000.0
    cash = ARCH_STARTING_CAPITAL
    FRICTION_PCT = arch_config.get("friction_pct", 0.0015)
    MAX_WEIGHT_PER_TRADE = 0.20
    open_positions = {}
    daily_equity_curve = []
    trades_log = []
    daily_exposure_log = []
    high_water_mark = cash
    
    # Pre-calculate Breakout Continuation Rate (BCR) for regime-adaptive architectures
    bcr_series = {}
    breadth_series = {}  # % of stocks with Close > 50-day SMA — purely historical per day
    if arch_config.get("regime_adaptive"):
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
                        
                    high, low, close = row['High'], row['Low'], row['Close']
                    pos['current_price'] = close
                    
                    if low <= pos['stop_loss']:
                        exit_price = pos['stop_loss']
                        net_entry_cost = pos['entry_price'] * (1 + FRICTION_PCT)
                        net_exit_revenue = exit_price * (1 - FRICTION_PCT)
                        pnl = (net_exit_revenue - net_entry_cost) / net_entry_cost
                        cash += pos['shares'] * exit_price * (1 - FRICTION_PCT)
                        symbols_to_remove.append(sym)
                        
                        trades_log.append({
                            "symbol": sym, 
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
            
        current_equity_for_hwm = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        if current_equity_for_hwm > high_water_mark:
            high_water_mark = current_equity_for_hwm
            
        risk_multiplier = 1.0
        if arch_config.get("dynamic_risk_scaling"):
            current_drawdown = (current_equity_for_hwm - high_water_mark) / high_water_mark
            if current_drawdown < -0.05:
                penalty = (abs(current_drawdown) - 0.05) * 5.0
                risk_multiplier = max(0.20, 1.0 - penalty)
                
        # 2. Evaluate new candidates
        new_candidates = []
        if cash > (5_00_000.0 * 0.05):
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
                    
            if not market_regime_blocked:
                for sym, df in bulk_data.items():
                    if sym == "NIFTYBEES":
                        continue
                    if sym in open_positions:
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
                    
                    # Architecture Logic
                    sizing_logic = arch_config.get('sizing_logic', 'primary_only')
                    risk_pct = 0.0
                    
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
                                risk_pct = 0.025
                                is_confirmed = True
                            else:
                                risk_pct = 0.01
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
                        close = hist_df['Close'].iloc[-1]
                        atr = talib.ATR(hist_df['High'], hist_df['Low'], hist_df['Close'], timeperiod=14).iloc[-1]
                        if pd.notna(atr) and atr > 0:
                            risk_atr = primary.get('risk_atr', 2.0)
                            reward_atr = primary.get('reward_atr', 4.0)
                            
                            # A2+A3: Adaptive Risk/Reward based on confirmation
                            if arch_config.get("adaptive_rr") and sizing_logic == "alpha_confirmation":
                                if is_confirmed:
                                    risk_atr = 1.5    # Tighter stop on high conviction
                                    reward_atr = 5.0   # Let right tail run
                                else:
                                    risk_atr = 2.5    # Wider stop on lower conviction
                                    reward_atr = 4.0   # Standard target
                            
                            alpha_score = p_res.get('alpha_score', 0.0) if p_res else 0.0
                            new_candidates.append({
                                "symbol": sym,
                                "price": close,
                                "stop_loss": close - (atr * risk_atr),
                                "target": close + (atr * reward_atr),
                                "risk_pct": risk_pct,
                                "alpha_score": alpha_score
                            })
                            
        # Allocate cash
        if new_candidates:
            # Rank candidates by alpha score (best first) if enabled
            if arch_config.get("rank_candidates"):
                new_candidates.sort(key=lambda x: x.get('alpha_score', 0.0), reverse=True)
            
            total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
            max_alloc_per_trade = total_equity * MAX_WEIGHT_PER_TRADE * risk_multiplier
            
            if "portfolio_cap" in arch_config:
                portfolio_cap = arch_config.get("portfolio_cap", 1.0)
                max_total_allocation = total_equity * portfolio_cap
                current_invested = sum(p['shares'] * p['current_price'] for p in open_positions.values())
                available_allocation = max_total_allocation - current_invested
                
                ideal_allocations = []
                for cand in new_candidates:
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
                    final_shares = int(alloc['ideal_shares'] * scaling_factor)
                    required_cash = final_shares * cand['price'] * (1 + FRICTION_PCT)
                    
                    if final_shares > 0 and cash >= required_cash:
                        cash -= required_cash
                        open_positions[cand['symbol']] = {
                            "shares": final_shares,
                            "entry_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": cand['price'],
                            "current_price": cand['price'],
                            "stop_loss": cand['stop_loss'],
                            "target": cand['target']
                        }
            else:
                for cand in new_candidates:
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
                            "entry_date": current_date.strftime("%Y-%m-%d"),
                            "entry_price": cand['price'],
                            "current_price": cand['price'],
                            "stop_loss": cand['stop_loss'],
                            "target": cand['target']
                        }
                    
        total_equity = cash + sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_equity_curve.append(total_equity)
        
        invested = sum(p['shares'] * p['current_price'] for p in open_positions.values())
        daily_exposure_log.append({
            "Date": current_date.strftime("%Y-%m-%d"),
            "Total_Equity": total_equity,
            "Invested": invested,
            "Exposure_Pct": invested / total_equity if total_equity > 0 else 0,
            "Num_Positions": len(open_positions),
            "Risk_Multiplier": risk_multiplier
        })
        
    metrics = calculate_metrics(daily_equity_curve, trades_log)
    metrics["Strategy"] = arch_config["name"]
    
    # Save daily exposure log
    safe_name = arch_config['name'].replace(' ', '_').replace(':', '')
    pd.DataFrame(daily_exposure_log).to_csv(f"/Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/front_testing/{safe_name}_exposure.csv", index=False)
    
    # Calculate Regime Breakdown
    nifty_full = bulk_data.get("NIFTYBEES")
    regime_metrics = calculate_regime_metrics(trades_log, nifty_full)
    metrics.update(regime_metrics)
    
    return metrics, daily_equity_curve, trades_log


def main():
    # Backtest covers exactly the last 4 years
    from datetime import datetime, timedelta
    # ⚠️ DO NOT CHANGE years_to_test for architectural comparison runs.
    # The full 6-year window is required to capture both the bull regime (2020-2024)
    # and the mean-reverting regime (2024-2026). Reducing to 2 years only shows
    # the recent bad period and makes ALL strategies look broken.
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

    # Find strategy definitions
    rs_strat = next(s for s in STRATEGIES if s["name"] == "Relative Strength")
    mom_strat = next(s for s in STRATEGIES if s["name"] == "Momentum Breakout")
    vol_strat = next(s for s in STRATEGIES if s["name"] == "Volatility Compression")
    
    # Define mean-reversion strategies for E11/E12
    oversold_strat = {"name": "Oversold Uptrend", "func": oversold_uptrend_eval, "risk_atr": 2.0, "reward_atr": 4.0}
    pullback_strat = {"name": "Trend Pullback", "func": trend_pullback_eval, "risk_atr": 2.0, "reward_atr": 4.0}
    
    ARCHITECTURES = [
        {
            "name": "E11_Regime_Adaptive",
            "primary": rs_strat,
            "primary_momentum": rs_strat,
            "confirmation_momentum": mom_strat,
            "primary_meanrev": oversold_strat,
            "confirmation_meanrev": pullback_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": True,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": 0.52
            # No cash_preservation — always finds a signal (State 1 or State 2)
        },
        {
            "name": "E12_Three_State",
            "primary": rs_strat,
            "primary_momentum": rs_strat,
            "confirmation_momentum": mom_strat,
            "primary_meanrev": oversold_strat,
            "confirmation_meanrev": pullback_strat,
            "sizing_logic": "alpha_confirmation",
            "dynamic_risk_scaling": True,
            "dd_penalty_factor": 5.0,
            "friction_pct": 0.0015,
            "rank_candidates": True,
            "regime_adaptive": True,
            "bcr_threshold": 0.52,   # Principled: above coin flip = trend-persistent
            "cash_preservation": True,
            "breadth_threshold": 0.30  # Principled: <30% stocks above SMA50 = extreme weakness
        }
    ]
    
    tear_sheet_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))), "front_testing", "strategy_tear_sheet.csv")
    
    from concurrent.futures import ProcessPoolExecutor, as_completed
    
    logger.info(f"Starting parallel architectural experiments using ProcessPoolExecutor...")
    
    futures = {}
    with ProcessPoolExecutor(max_workers=len(ARCHITECTURES)) as executor:
        for arch in ARCHITECTURES:
            future = executor.submit(
                run_architectural_backtest, 
                arch, 
                test_dates, 
                bulk_data, 
                industry_mapping, 
                sector_indices
            )
            futures[future] = arch
            
        for future in as_completed(futures):
            arch = futures[future]
            try:
                metrics, curve, trades = future.result()
                results.append(metrics)
                curves[arch['name']] = curve
                
                # Save trades log
                if trades:
                    trades_df = pd.DataFrame(trades)
                    safe_name = arch['name'].replace(" ", "_").replace(":", "")
                    trades_csv_path = os.path.join(os.path.dirname(tear_sheet_path), f"{safe_name}_backtest_trades.csv")
                    trades_df.to_csv(trades_csv_path, index=False)
            except Exception as e:
                logger.error(f"Error backtesting {arch['name']}: {e}")
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
    logger.info(f"Appended results to {experiment_log_path}")
    years = round(calendar_days_since_start / 365, 1)
    print(f"\n================= STRATEGY TEAR SHEET (LAST {years} YEARS) =================")
    print(results_df.to_string())
    print("======================================================================\n")

if __name__ == "__main__":
    main()