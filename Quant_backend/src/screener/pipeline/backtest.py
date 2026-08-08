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
    
    # Extract a master list of all unique trading dates from the loaded data
    all_dates = set()
    for df in bulk_data.values():
        if not df.empty:
            all_dates.update(df.index.tolist())
            
    sorted_dates = sorted(list(all_dates))
    
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
    
    # 2. Iterate chronologically
    for i, current_date in enumerate(test_dates):
        if i % 10 == 0:
            logger.info(f"Processing date {current_date.date()} ({i}/{len(test_dates)})...")
            
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
            
            passed_bb = bb_trigger.get("passed", False)
            passed_ma = ma_trigger.get("passed", False)
            
            if passed_bb or passed_ma:
                trigger_types = []
                if passed_bb: trigger_types.append("Bollinger Breakout")
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
                
            # Calculate 20 SMA on the fly for the forward slice
            df_forward = df.copy()
            df_forward['SMA_20'] = df_forward['Close'].rolling(window=20).mean()
            
            exit_idx = -1
            # Check exit (Close < 20 SMA)
            for j in range(t_idx + 1, len(df_forward)):
                close = df_forward['Close'].iloc[j]
                sma20 = df_forward['SMA_20'].iloc[j]
                if pd.notna(sma20) and close < sma20:
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
            # Drop NaNs for active trades
            r5 = group["ret_5d"].dropna()
            r10 = group["ret_10d"].dropna()
            r20 = group["ret_20d"].dropna()
            e5 = group["exc_5d"].dropna()
            e10 = group["exc_10d"].dropna()
            e20 = group["exc_20d"].dropna()
            mdds = group["mdd"].dropna()
            
            n_5d = len(r5)
            n_10d = len(r10)
            n_20d = len(r20)
            
            assert n_5d == n_10d == n_20d, f"CRITICAL: Sample size mismatch! 5d: {n_5d}, 10d: {n_10d}, 20d: {n_20d}"
            
            hr5 = (r5 > 0).mean() * 100 if n_5d > 0 else 0
            hr10 = (r10 > 0).mean() * 100 if n_10d > 0 else 0
            hr20 = (r20 > 0).mean() * 100 if n_20d > 0 else 0
            
            avg_r5 = r5.mean() * 100 if n_5d > 0 else 0
            avg_r10 = r10.mean() * 100 if n_10d > 0 else 0
            avg_r20 = r20.mean() * 100 if n_20d > 0 else 0
            
            avg_e5 = e5.mean() * 100 if n_5d > 0 else 0
            avg_e10 = e10.mean() * 100 if n_10d > 0 else 0
            avg_e20 = e20.mean() * 100 if n_20d > 0 else 0
            
            avg_mdd = mdds.mean() * 100 if len(mdds) > 0 else 0
            
            # Calculate clustering
            pairs = list(zip(group["symbol"], group["date"]))
            pairs.sort(key=lambda x: x[1])  # sort by date
            unique_dates = len(set([d for s, d in pairs]))
            
            logger.info(f"Trigger: [{trigger}] (Total Signals: {count} | Valid Forward N: {n_20d})")
            logger.info(f"  Clustering: {count} signals occurred across {unique_dates} unique dates")
            logger.info(f"  Hit Rate (Win %):  5d(n={n_5d}): {hr5:.1f}% | 10d(n={n_10d}): {hr10:.1f}% | 20d(n={n_20d}): {hr20:.1f}%")
            logger.info(f"  Avg Return (%):    5d(n={n_5d}): {avg_r5:+.2f}% | 10d(n={n_10d}): {avg_r10:+.2f}% | 20d(n={n_20d}): {avg_r20:+.2f}%")
            logger.info(f"  Avg Excess Ret:    5d(n={n_5d}): {avg_e5:+.2f}% | 10d(n={n_10d}): {avg_e10:+.2f}% | 20d(n={n_20d}): {avg_e20:+.2f}%")
            logger.info(f"  Avg Max Drawdown: {avg_mdd:.2f}%")
            logger.info("  Signal Instances:")
            for s, d in pairs:
                logger.info(f"    - {s} on {d.date()}")
                
            logger.info("  Symbol Breakdown (Trades | Avg 20d Return):")
            sym_stats = group.groupby("symbol").agg(
                trades=("ret_20d", "count"),
                avg_r20=("ret_20d", "mean")
            ).reset_index()
            sym_stats.sort_values(by=["trades", "avg_r20"], ascending=[False, False], inplace=True)
            for _, row in sym_stats.iterrows():
                avg_pct = row['avg_r20'] * 100
                logger.info(f"    - {row['symbol']:<12}: {row['trades']} trades | {avg_pct:+.2f}%")
                
            logger.info("  --- Fibonacci Confluence Split (Exploratory, Low Sample Size) ---")
            for pocket_status in [True, False]:
                subgroup = group[group["in_golden_pocket"] == pocket_status]
                n_sub = len(subgroup)
                if n_sub == 0:
                    continue
                
                r20_sub = subgroup["ret_20d"].dropna()
                if len(r20_sub) == 0:
                    continue
                    
                hr20_sub = (r20_sub > 0).mean() * 100
                avg_r20_sub = r20_sub.mean() * 100
                avg_e20_sub = subgroup["exc_20d"].dropna().mean() * 100
                
                label = "in golden pocket" if pocket_status else "not in golden pocket"
                warning = " [WARNING: n<10]" if n_sub < 10 else ""
                
                logger.info(f"    - {label} (n={n_sub}){warning}: Hit Rate 20d: {hr20_sub:.1f}% | Avg Ret 20d: {avg_r20_sub:+.2f}% | Avg Exc 20d: {avg_e20_sub:+.2f}%")
                
            # Placebo Test for statistical significance
            if count >= 10:
                valid_group = group.dropna(subset=["exc_20d"])
                if len(valid_group) > 0:
                    in_group = valid_group[valid_group["in_golden_pocket"] == True]
                    out_group = valid_group[valid_group["in_golden_pocket"] == False]
                    
                    n_in = len(in_group)
                    n_out = len(out_group)
                    
                    if n_in > 0 and n_out > 0:
                        real_in_exc = in_group["exc_20d"].mean()
                        real_out_exc = out_group["exc_20d"].mean()
                        real_gap = real_in_exc - real_out_exc
                        
                        all_exc = valid_group["exc_20d"].values
                        gaps = []
                        
                        # Use a fixed seed for reproducibility across runs
                        np.random.seed(42)
                        for _ in range(1000):
                            shuffled = np.random.permutation(all_exc)
                            sim_in = shuffled[:n_in].mean()
                            sim_out = shuffled[n_in:].mean()
                            gaps.append(sim_in - sim_out)
                            
                        gaps = np.array(gaps)
                        percentile = (gaps < real_gap).mean() * 100
                        
                        logger.info(f"  --- Placebo Test (1000 Shuffles) ---")
                        logger.info(f"    - Real Excess Gap: {real_gap*100:+.2f} pts")
                        logger.info(f"    - Significance: {percentile:.1f}th percentile vs random shuffles")
                        if percentile > 90:
                            logger.info(f"    - [SIGNIFICANT] The golden pocket edge is likely real.")
                        else:
                            logger.info(f"    - [NOT SIGNIFICANT] Indistinguishable from randomly splitting the same signals.")
                            
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
            total_return = np.sum(returns_series)
            cagr = ((1 + total_return) ** (1/years) - 1) * 100 if years > 0 else 0
            
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
