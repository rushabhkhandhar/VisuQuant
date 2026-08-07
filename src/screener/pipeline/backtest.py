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

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_backtest(months: int = 3):
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
    universe = load_nifty500_symbols()
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
                
                for tt in trigger_types:
                    sig_dict = {
                        "date": current_date,
                        "symbol": symbol,
                        "trigger_type": tt
                    }
                    
                    # Always add to raw
                    raw_signals.append(sig_dict)
                    
                    # Check dedup
                    last_idx = last_signal_idx.get((symbol, tt), -999)
                    if t_idx - last_idx >= config.DEDUP_WINDOW_DAYS:
                        deduped_signals.append(sig_dict)
                        last_signal_idx[(symbol, tt)] = t_idx
                
    logger.info(f"Backtest generated {len(raw_signals)} RAW signals and {len(deduped_signals)} DEDUPED signals.")
    
    # 3. Compute Forward Returns
    def compute_metrics(sig_list):
        results = []
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
            # We also rigidly require a full 20 trading days of forward data to exist, 
            # otherwise we silently drop the signal entirely from all metrics to keep sample size constant.
            if t_idx + 1 + 20 >= len(df):
                continue 
                
            entry_price = df['Open'].iloc[t_idx + 1]
            if pd.isna(entry_price) or entry_price == 0:
                continue
                
            # Get exact forward returns (Net of Costs)
            ret_5d = ((df['Close'].iloc[t_idx + 1 + 5] - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
            ret_10d = ((df['Close'].iloc[t_idx + 1 + 10] - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
            ret_20d = ((df['Close'].iloc[t_idx + 1 + 20] - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
            
            # Benchmark relative returns
            excess_5d, excess_10d, excess_20d = 0.0, 0.0, 0.0
            bm_df = bulk_data.get("NIFTYBEES")
            if bm_df is not None:
                entry_date = df.index[t_idx + 1]
                try:
                    bm_t_idx = bm_df.index.get_loc(entry_date)
                    if bm_t_idx + 20 < len(bm_df):
                        bm_entry = bm_df['Open'].iloc[bm_t_idx]
                        if not pd.isna(bm_entry) and bm_entry > 0:
                            bm_ret_5d = (bm_df['Close'].iloc[bm_t_idx + 5] - bm_entry) / bm_entry
                            bm_ret_10d = (bm_df['Close'].iloc[bm_t_idx + 10] - bm_entry) / bm_entry
                            bm_ret_20d = (bm_df['Close'].iloc[bm_t_idx + 20] - bm_entry) / bm_entry
                            excess_5d = ret_5d - bm_ret_5d
                            excess_10d = ret_10d - bm_ret_10d
                            excess_20d = ret_20d - bm_ret_20d
                except KeyError:
                    pass
            
            # Max Drawdown over the next 20 days (from entry price, net of cost)
            future_20d = df.iloc[t_idx + 1 : t_idx + 1 + 20]
            min_low = future_20d['Low'].min()
            max_drawdown = ((min_low - entry_price) / entry_price) - config.ROUND_TRIP_COST_PCT
                
            results.append({
                "trigger": sig["trigger_type"],
                "symbol": sig["symbol"],
                "date": sig["date"],
                "ret_5d": ret_5d,
                "ret_10d": ret_10d,
                "ret_20d": ret_20d,
                "exc_5d": excess_5d,
                "exc_10d": excess_10d,
                "exc_20d": excess_20d,
                "mdd": max_drawdown
            })
            
        return results

    
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
            logger.info("\n")

    raw_results = compute_metrics(raw_signals)
    dedup_results = compute_metrics(deduped_signals)
    
    report_statistics(raw_results, "RAW (NON-DEDUPED)")
    report_statistics(dedup_results, "DEDUPED")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run lightweight quantitative backtest.")
    parser.add_argument("--months", type=int, default=3, help="Months of historical data to backtest over.")
    args = parser.parse_args()
    
    run_backtest(months=args.months)
