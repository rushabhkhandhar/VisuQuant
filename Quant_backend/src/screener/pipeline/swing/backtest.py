import pandas as pd
import numpy as np
import logging
from datetime import date, timedelta
from typing import List, Dict
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.screener import config
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.screener.screens.vcp_trend_template import evaluate_vcp_trend
from src.screener.screens.trigger_layer import bollinger_squeeze_breakout, ma_pullback_bounce
from src.screener.screens.fib_confluence import get_golden_pocket
from src.screener.screens.donchian_breakout import donchian_breakout
from src.screener.screens.connors_rsi import connors_rsi_pullback

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_backtest(months: int = 3, symbols: List[str] = None, return_json: bool = False):
    """
    Lightweight backtester for the quantitative screener.
    Runs the screening logic over historical data and computes forward returns.
    """
    logger.info(f"--- Starting Backtest over last {months} months ---")
    logger.info(f"Pipeline Config: STAGE1_FILTER_ENABLED = {config.STAGE1_FILTER_ENABLED}")
    
    # Calculate trading days
    backtest_days = months * 21
    # We need 300 days of history BEFORE the start of the backtest to compute 200 SMA
    total_lookback = backtest_days + 300 
    
    # 1. Load Universe and Data
    universe = load_nifty500_symbols() if not symbols else symbols
    logger.info(f"Loaded {len(universe)} symbols. Fetching bulk history for {total_lookback} days...")
    
    # Ensure benchmark is in universe for relative returns
    if "NIFTYBEES" not in universe:
        universe.append("NIFTYBEES")
        
    # Fetch all data once for extreme speed
    bulk_data = fetch_bulk_history(universe, date.today(), lookback_days=total_lookback)
    
    # Use NIFTYBEES as the source of truth for trading days to avoid phantom dates
    nifty_df = bulk_data.get("NIFTYBEES")
    if nifty_df is None or nifty_df.empty:
        logger.error("NIFTYBEES missing from bulk data. Cannot align dates.")
        return
        
    sorted_dates = sorted(nifty_df.index.tolist())
    
    if len(sorted_dates) <= backtest_days:
        logger.error("Not enough data fetched for backtest.")
        return
        
    # The dates we will actually run the screener on
    test_dates = sorted_dates[-backtest_days:]
    logger.info(f"Running historical screen over {len(test_dates)} trading days...")
    
    # We will track both for comparison
    raw_signals = []
    deduped_signals = []
    last_signal_idx = {} # (symbol, trigger_type) -> t_idx
    
    # Pre-compute NIFTY 200 SMA for regime filtering
    nifty_df = bulk_data.get("NIFTYBEES")
    if nifty_df is not None and not nifty_df.empty:
        nifty_df['SMA_200'] = nifty_df['Close'].rolling(window=200).mean()
    
    # 2. Iterate chronologically
    for i, current_date in enumerate(test_dates):
        if i % 10 == 0:
            logger.info(f"Processing date {current_date.date()} ({i}/{len(test_dates)})...")
            
        # Regime Filter Check
        is_bull_regime = True
        if nifty_df is not None:
            try:
                t_idx = nifty_df.index.get_loc(current_date)
                nifty_close = nifty_df['Close'].iloc[t_idx]
                nifty_sma200 = nifty_df['SMA_200'].iloc[t_idx]
                if pd.notna(nifty_sma200) and nifty_close < nifty_sma200:
                    is_bull_regime = False
            except KeyError:
                pass
                
        if not is_bull_regime:
            continue  # Skip taking ANY new trades if broader market is in a bear regime
            
        daily_trend_survivors = []
        for symbol, df in bulk_data.items():
            if df.empty:
                continue
                
            # SLICE the dataframe up to the current date strictly. 
            # This completely eliminates lookahead bias for indicator calculation.
            # RISK FLAG: We use the Close of current_date for the signal. 
            # In live trading, this assumes we either execute exactly at the closing auction, 
            # or the next day's open. For backtesting, we will use next day's open as entry.
            historical_df = df.loc[df.index <= current_date]
            
            # Need at least 200 days for Stage 1
            if len(historical_df) < 200:
                continue
                
            # Check Liquidity on the sliced data
            df_20d = historical_df.tail(20)
            avg_20d_value = ((df_20d['Close'] * df_20d['Volume']) / 10_000_000).mean()
            if avg_20d_value < config.LIQUIDITY_MIN_VALUE_CR:
                continue
                
            # Stage 1: VCP Trend (Optional)
            if config.STAGE1_FILTER_ENABLED:
                trend_metrics = evaluate_vcp_trend(historical_df, config.NEAR_52W_HIGH_PCT)
                if not trend_metrics.get("passed", False):
                    continue
                    
                daily_trend_survivors.append({
                    "symbol": symbol,
                    "df": historical_df,
                    "atr_ratio": trend_metrics.get("atr_ratio", 1.0)
                })
            else:
                daily_trend_survivors.append({
                    "symbol": symbol,
                    "df": historical_df,
                    "atr_ratio": 1.0
                })
            
        if not daily_trend_survivors:
            continue
            
        final_survivors = []
        if config.STAGE1_FILTER_ENABLED:
            # Cross-sectional ATR filtration
            atr_ratios = [x["atr_ratio"] for x in daily_trend_survivors]
            cutoff = np.percentile(atr_ratios, config.ATR_CONTRACTION_PERCENTILE)
            
            for cand in daily_trend_survivors:
                if cand["atr_ratio"] <= cutoff:
                    final_survivors.append(cand)
        else:
            final_survivors = daily_trend_survivors
                
        for cand in final_survivors:
            symbol = cand["symbol"]
            historical_df = cand["df"]
            
            # Stage 2: Triggers
            bb_trigger = bollinger_squeeze_breakout(historical_df, config.BB_LOOKBACK_MONTHS, config.VOLUME_BREAKOUT_MULT)
            ma_trigger = ma_pullback_bounce(historical_df)
            dc_trigger = donchian_breakout(historical_df)
            crsi_trigger = connors_rsi_pullback(historical_df)
            
            passed_bb = bb_trigger.get("passed", False)
            passed_ma = ma_trigger.get("passed", False)
            passed_dc = dc_trigger.get("passed", False)
            passed_crsi = crsi_trigger.get("passed", False)
            
            if passed_bb or passed_ma or passed_dc or passed_crsi:
                trigger_types = []
                if passed_bb: trigger_types.append("Bollinger Breakout")
                if passed_dc: trigger_types.append("Donchian Breakout")
                if passed_crsi: trigger_types.append("ConnorsRSI Pullback")
                if passed_ma: trigger_types.append(f"{ma_trigger.get('reversal_type', 'MA Bounce')}")
                
                t_idx = historical_df.index.get_loc(current_date)
                
                trigger_high = historical_df['High'].iloc[-1]
                trigger_low = historical_df['Low'].iloc[-1]
                fib_metrics = get_golden_pocket(historical_df, as_of_date=current_date, min_swing_pct=config.FIB_MIN_SWING_PCT)
                
                in_golden_pocket = False
                if fib_metrics:
                    if trigger_low <= fib_metrics["pocket_high"] and trigger_high >= fib_metrics["pocket_low"]:
                        in_golden_pocket = True
                
                for tt in trigger_types:
                    sig_dict = {
                        "date": current_date,
                        "symbol": symbol,
                        "trigger_type": tt,
                        "in_golden_pocket": in_golden_pocket
                    }
                    
                    # Always add to raw
                    raw_signals.append(sig_dict)
                    
                    # Check dedup
                    last_idx = last_signal_idx.get((symbol, tt), -999)
                    if t_idx - last_idx >= config.DEDUP_WINDOW_DAYS:
                        deduped_signals.append(sig_dict)
                        last_signal_idx[(symbol, tt)] = t_idx
                
    logger.info(f"Backtest generated {len(raw_signals)} RAW signals and {len(deduped_signals)} DEDUPED signals.")
    
    # 3. Compute Forward Returns (Dynamic Trailing Stop)
    def compute_metrics(sig_list):
        results = []
        trades_for_json = []
        
        for sig in sig_list:
            symbol = sig["symbol"]
            t_date = sig["date"]
            df = bulk_data[symbol]
            
            # Find the index of the trigger date
            try:
                t_idx = df.index.get_loc(t_date)
            except KeyError:
                continue
                
            # We assume entry is at the Next Day's Open to avoid EOD lookahead execution bias.
            if t_idx + 1 >= len(df):
                continue 
                
            entry_price = df['Open'].iloc[t_idx + 1]
            if pd.isna(entry_price) or entry_price == 0:
                continue
                
            # Calculate ATR(22) for the forward slice manually to avoid pandas_ta dependency issues
            df_forward = df.copy()
            high_low = df_forward['High'] - df_forward['Low']
            high_close = np.abs(df_forward['High'] - df_forward['Close'].shift())
            low_close = np.abs(df_forward['Low'] - df_forward['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            df_forward['ATR_22'] = true_range.rolling(config.CHANDELIER_ATR_PERIOD).mean()
            
            exit_idx = -1
            highest_high = df_forward['High'].iloc[t_idx + 1]
            
            # Check exit (Chandelier Exit: Close < Highest High - 3*ATR)
            for j in range(t_idx + 1, len(df_forward)):
                close = df_forward['Close'].iloc[j]
                high = df_forward['High'].iloc[j]
                atr = df_forward['ATR_22'].iloc[j]
                
                # Update highest high since entry
                if high > highest_high:
                    highest_high = high
                    
                if pd.notna(atr):
                    stop_loss = highest_high - (config.CHANDELIER_ATR_MULT * atr)
                    if close < stop_loss:
                        exit_idx = j
                        break
            
            if exit_idx == -1:
                # Still open, exit at the last bar
                exit_idx = len(df_forward) - 1
                
            exit_price = df_forward['Close'].iloc[exit_idx]
            trade_return = ((exit_price - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
            
            # Max Drawdown over the trade duration
            trade_duration_df = df_forward.iloc[t_idx + 1 : exit_idx + 1]
            if len(trade_duration_df) > 0:
                min_low = trade_duration_df['Low'].min()
                max_drawdown = ((min_low - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
            else:
                max_drawdown = trade_return
                
            exit_date = df_forward.index[exit_idx]
            
            trades_for_json.append({
                "symbol": symbol,
                "entry_date": str(df_forward.index[t_idx+1].date()),
                "exit_date": str(exit_date.date()),
                "entry_price": float(entry_price),
                "exit_price": float(exit_price),
                "return": float(trade_return)
            })
            
            results.append({
                "trigger": sig["trigger_type"],
                "symbol": sig["symbol"],
                "date": sig["date"],
                "ret_dyn": trade_return,
                "mdd": max_drawdown,
                "in_golden_pocket": sig.get("in_golden_pocket", False)
            })
            
        return results, trades_for_json

    
    # 4. Report Statistics
    def report_statistics(results, title):
        if not results:
            logger.warning(f"No measurable signals found for {title}.")
            return
            
        res_df = pd.DataFrame(results)
        
        logger.info("\n=========================================")
        logger.info(f"     {title} BACKTEST RESULTS     ")
        logger.info("=========================================\n")
        
        # Clean string so multi-triggers don't break grouping (or we can group them as is)
        groups = res_df.groupby("trigger")
        
        for trigger, group in groups:
            count = len(group)
            
            dyn_rets = group["ret_dyn"].dropna()
            mdds = group["mdd"].dropna()
            
            n_trades = len(dyn_rets)
            win_rate = (dyn_rets > 0).mean() * 100 if n_trades > 0 else 0
            avg_ret = dyn_rets.mean() * 100 if n_trades > 0 else 0
            avg_mdd = mdds.mean() * 100 if len(mdds) > 0 else 0
            
            # Calculate clustering
            pairs = list(zip(group["symbol"], group["date"]))
            pairs.sort(key=lambda x: x[1])  # sort by date
            unique_dates = len(set([d for s, d in pairs]))
            
            logger.info(f"Trigger: [{trigger}] (Total Signals: {count})")
            logger.info(f"  Clustering: {count} signals occurred across {unique_dates} unique dates")
            logger.info(f"  Hit Rate (Win %): {win_rate:.1f}%")
            logger.info(f"  Avg Return (%): {avg_ret:+.2f}%")
            logger.info(f"  Avg Max Drawdown: {avg_mdd:.2f}%")
            logger.info("  Signal Instances:")
            for s, d in pairs:
                logger.info(f"    - {s} on {d.date()}")
                
            logger.info("  Symbol Breakdown (Trades | Avg Return):")
            sym_stats = group.groupby("symbol").agg(
                trades=("ret_dyn", "count"),
                avg_ret=("ret_dyn", "mean")
            ).reset_index()
            sym_stats.sort_values(by=["trades", "avg_ret"], ascending=[False, False], inplace=True)
            for _, row in sym_stats.iterrows():
                avg_pct = row['avg_ret'] * 100
                logger.info(f"    - {row['symbol']:<12}: {row['trades']} trades | {avg_pct:+.2f}%")
                
            logger.info("  --- Fibonacci Confluence Split (Exploratory, Low Sample Size) ---")
            for pocket_status in [True, False]:
                subgroup = group[group["in_golden_pocket"] == pocket_status]
                n_sub = len(subgroup)
                if n_sub == 0:
                    continue
                
                dyn_sub = subgroup["ret_dyn"].dropna()
                if len(dyn_sub) == 0:
                    continue
                    
                hr_sub = (dyn_sub > 0).mean() * 100
                avg_ret_sub = dyn_sub.mean() * 100
                
                label = "in golden pocket" if pocket_status else "not in golden pocket"
                warning = " [WARNING: n<10]" if n_sub < 10 else ""
                
                logger.info(f"    - {label} (n={n_sub}){warning}: Hit Rate: {hr_sub:.1f}% | Avg Ret: {avg_ret_sub:+.2f}%")
                            
            logger.info("\n")

    raw_results, raw_trades = compute_metrics(raw_signals)
    dedup_results, dedup_trades = compute_metrics(deduped_signals)
    
    # We omit the legacy logger outputs to focus on JSON if requested
    if return_json:
        # Calculate JSON metrics on deduped results
        wins = [t['return'] for t in dedup_trades if t['return'] > 0]
        losses = [t['return'] for t in dedup_trades if t['return'] <= 0]
        
        win_rate = len(wins) / len(dedup_trades) * 100 if dedup_trades else 0
        avg_win = np.mean(wins) * 100 if wins else 0
        avg_loss = np.mean(losses) * 100 if losses else 0
        
        cagr = 0
        max_drawdown = 0
        sharpe = 0
        sortino = 0
        calmar = 0
        
        if dedup_trades:
            # Build a synthetic daily equity curve
            returns_series = pd.Series([t['return'] for t in dedup_trades])
            mdds = [r['mdd'] for r in dedup_results]
            max_drawdown = min(mdds) * 100 if mdds else 0
            
            years = months / 12
            compounded_growth = np.prod(1 + returns_series)
            total_return = compounded_growth - 1
            cagr = (compounded_growth ** (1/years) - 1) * 100 if years > 0 else 0
            
            daily_rf = 0.05 / 252
            daily_returns = returns_series # Approximate trade returns as daily for ratio estimation in JSON
            excess_returns = daily_returns - daily_rf
            sharpe = (excess_returns.mean() / daily_returns.std()) * np.sqrt(252) if daily_returns.std() != 0 and not pd.isna(daily_returns.std()) else 0
            
            downside_returns = daily_returns[daily_returns < 0]
            downside_vol = downside_returns.std() * np.sqrt(252) if not downside_returns.empty else 0
            sortino = (excess_returns.mean() * 252 / downside_vol) if downside_vol != 0 and not pd.isna(downside_vol) else 0
            if pd.isna(sortino) or np.isinf(sortino): sortino = 0
            if pd.isna(sharpe) or np.isinf(sharpe): sharpe = 0
            if pd.isna(cagr) or np.isinf(cagr): cagr = 0
            if pd.isna(calmar) or np.isinf(calmar): calmar = 0
            
            calmar = (cagr / abs(max_drawdown)) if max_drawdown != 0 else 0
            if pd.isna(calmar) or np.isinf(calmar): calmar = 0
            
        metrics = {
            "Total Trades": len(dedup_trades),
            "Win Rate (%)": round(win_rate, 2),
            "Average Win (%)": round(avg_win, 2),
            "Average Loss (%)": round(avg_loss, 2),
            "Max Drawdown (%)": round(max_drawdown, 2),
            "CAGR (%)": round(cagr, 2),
            "Sharpe Ratio": round(sharpe, 2),
            "Sortino Ratio": round(sortino, 2),
            "Calmar Ratio": round(calmar, 2)
        }
        
        return {
            "symbol": symbols[0] if symbols and len(symbols) == 1 else "BASKET",
            "period": f"{months}mo",
            "metrics": metrics,
            "trades": dedup_trades
        }
    
    report_statistics(raw_results, "RAW (NON-DEDUPED)")
    report_statistics(dedup_results, "DEDUPED")
    
    return dedup_results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run lightweight quantitative backtest.")
    parser.add_argument("--months", type=int, default=3, help="Months of historical data to backtest over.")
    args = parser.parse_args()
    
    run_backtest(months=args.months)
