import argparse
import logging
from datetime import date
from typing import List, Dict, Any
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../..')))

from src.screener import config
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.screener.screens.liquidity import filter_by_liquidity
from src.screener.screens.vcp_trend_template import evaluate_vcp_trend
from src.screener.screens.trigger_layer import bollinger_squeeze_breakout, ma_pullback_bounce
from src.screener.screens.fib_confluence import get_golden_pocket
from src.screener.screens.donchian_breakout import donchian_breakout
from src.screener.screens.connors_rsi import connors_rsi_pullback
from src.screener.screens.relative_strength import compute_relative_strength
from src.screener.screens.fundamental_quality import evaluate_fundamentals

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_screener(as_of_date: date = None, dry_run: bool = False, top_n: int = 5, check_regime: bool = False) -> Dict[str, Any]:
    current_regime = "UNKNOWN"
    if as_of_date is None:
        as_of_date = date.today()
        
    logger.info(f"--- Starting Daily Quantitative Screen for {as_of_date} ---")
    
    # 1. Load Universe
    universe = load_nifty500_symbols()
        
    initial_count = len(universe)
    logger.info(f"Loaded initial universe: {initial_count} symbols.")
    
    if check_regime:
        logger.info("Checking current market regime (NIFTYBEES)...")
        bulk_data_nifty = fetch_bulk_history(["NIFTYBEES"], as_of_date, lookback_days=100)
        nifty = bulk_data_nifty.get("NIFTYBEES")
        if nifty is not None and not nifty.empty and len(nifty) >= 50:
            sma_50 = nifty["Close"].rolling(50).mean()
            sma_50_diff = sma_50.diff()
            
            curr_close = nifty["Close"].iloc[-1]
            curr_sma50 = sma_50.iloc[-1]
            curr_sma50_diff = sma_50_diff.iloc[-1]
            
            if curr_close > curr_sma50 and curr_sma50_diff > 0:
                current_regime = "TRENDING UP (Bullish)"
            elif curr_close < curr_sma50 and curr_sma50_diff < 0:
                current_regime = "TRENDING DOWN (Bearish)"
            else:
                current_regime = "CHOPPY (Neutral)"
                
            logger.info("=========================================")
            logger.info(f"   MARKET REGIME: {current_regime}   ")
            logger.info("=========================================")
        else:
            logger.warning("Could not fetch sufficient NIFTYBEES data to determine regime.")
    
    # 2. Liquidity Pre-Filter
    logger.info(f"Applying Liquidity Filter (>= {config.LIQUIDITY_MIN_VALUE_CR} Cr/day)...")
    liquid_symbols = filter_by_liquidity(universe, config.LIQUIDITY_MIN_VALUE_CR, as_of_date)
    liquidity_count = len(liquid_symbols)
    logger.info(f"Liquidity Survivors: {liquidity_count} symbols.")
    
    if liquidity_count == 0:
        logger.warning("Pipeline halted: 0 symbols survived liquidity filter.")
        return []
        
    # Fetch historical data for all liquid survivors (need ~300 days for 200 SMA + BB lookback)
    logger.info("Fetching bulk historical data for liquid universe (~300 days)...")
    bulk_data = fetch_bulk_history(liquid_symbols, as_of_date, lookback_days=300)
    
    import numpy as np
    
    # 3. Stage 1: VCP Trend Template
    pre_atr_survivors = {}
    stage1_survivors = {}
    cond_counts = {"c1": 0, "c2": 0, "c3": 0, "c5": 0, "all_trend": 0}
    
    if config.STAGE1_FILTER_ENABLED:
        logger.info("Running Stage 1: Minervini VCP Trend Template...")
        
        for symbol, df in bulk_data.items():
            if df.empty:
                continue
                
            trend_metrics = evaluate_vcp_trend(df, config.NEAR_52W_HIGH_PCT)
            
            # Log counts
            if trend_metrics.get("c1_sma", False): cond_counts["c1"] += 1
            if trend_metrics.get("c2_sma200_up", False): cond_counts["c2"] += 1
            if trend_metrics.get("c3_52w_high", False): cond_counts["c3"] += 1
            if trend_metrics.get("c5_vol_dry", False): cond_counts["c5"] += 1
            
            if trend_metrics.get("passed", False):
                cond_counts["all_trend"] += 1
                pre_atr_survivors[symbol] = {
                    "df": df,
                    "trend_metrics": trend_metrics
                }
                
        logger.info("--- VCP Diagnostic Counts ---")
        logger.info(f"C1 (SMA Stack): {cond_counts['c1']} passed")
        logger.info(f"C2 (200 SMA Up): {cond_counts['c2']} passed")
        logger.info(f"C3 (Near 52W High): {cond_counts['c3']} passed")
        logger.info(f"C5 (Vol Dry Up): {cond_counts['c5']} passed")
        logger.info(f"Passed All Core Trend: {cond_counts['all_trend']} passed")
        
        # Cross-sectional ATR filtration
        if pre_atr_survivors:
            atr_ratios = [data["trend_metrics"]["atr_ratio"] for data in pre_atr_survivors.values()]
            dynamic_cutoff = np.percentile(atr_ratios, config.ATR_CONTRACTION_PERCENTILE)
            logger.info(f"Dynamic ATR Threshold (Bottom {config.ATR_CONTRACTION_PERCENTILE}% of {len(atr_ratios)} survivors): {dynamic_cutoff:.2f}")
            
            for symbol, data in pre_atr_survivors.items():
                if data["trend_metrics"]["atr_ratio"] <= dynamic_cutoff:
                    stage1_survivors[symbol] = data
    else:
        logger.info("Skipping Stage 1 (VCP Trend Template) as STAGE1_FILTER_ENABLED is False.")
        for symbol, df in bulk_data.items():
            if not df.empty:
                stage1_survivors[symbol] = {"df": df, "trend_metrics": {}}
                
    stage1_count = len(stage1_survivors)
    if config.STAGE1_FILTER_ENABLED:
        logger.info(f"Stage 1 Final (Post-ATR) Survivors: {stage1_count} symbols.")
    else:
        logger.info(f"Candidates bypassing Stage 1: {stage1_count} symbols.")
    
    if stage1_count == 0:
        logger.warning("Pipeline halted: 0 symbols survived Stage 1.")
        return []
        
    # --- STAGE 1.5: Fundamental Quality Filter ---
    logger.info("Running Stage 1.5: Fundamental Quality (Screener.in)...")
    stage1_5_survivors = {}
    for symbol, data in stage1_survivors.items():
        logger.info(f"Checking fundamentals for {symbol}...")
        f_eval = evaluate_fundamentals(symbol)
        if f_eval.get("passed"):
            logger.info(f"  [PASS] {symbol}: ROE {f_eval.get('roe')}%, OP Growth {f_eval.get('op_growth')}, Inst Buying {f_eval.get('inst_buying')}")
            stage1_5_survivors[symbol] = data
        else:
            logger.info(f"  [FAIL] {symbol}: {', '.join(f_eval.get('reasons', []))}")
            
    stage1_5_count = len(stage1_5_survivors)
    logger.info(f"Stage 1.5 Final Survivors: {stage1_5_count} symbols.")
    
    if stage1_5_count == 0:
        logger.warning("Pipeline halted: 0 symbols survived Stage 1.5.")
        return []
        
    # 4 & 5. Stage 2: Trigger Layer & Fib Confluence
    if "TRENDING UP" in current_regime:
        base_regime = "TRENDING UP"
    elif "TRENDING DOWN" in current_regime:
        base_regime = "TRENDING DOWN"
    else:
        base_regime = "CHOPPY"
        
    logger.info(f"Running Stage 2: Trigger Layer (Dynamic Regime: {base_regime})...")
    
    active_config = config.REGIME_STRATEGIES.get(base_regime, {}).get("active", [])
    watchlist_config = config.REGIME_STRATEGIES.get(base_regime, {}).get("watchlist", [])
    disabled_config = config.REGIME_STRATEGIES.get(base_regime, {}).get("disabled", [])
    
    final_candidates = []
    watchlist_candidates = []
    
    for symbol, data in stage1_5_survivors.items():
        df = data["df"]
        trend_metrics = data["trend_metrics"]
        
        # Run ALL independent triggers
        bb_trigger = bollinger_squeeze_breakout(df, config.BB_LOOKBACK_MONTHS, config.VOLUME_BREAKOUT_MULT, disabled_triggers=disabled_config)
        ma_trigger = ma_pullback_bounce(df, disabled_triggers=disabled_config)
        dc_trigger = donchian_breakout(df, disabled_triggers=disabled_config)
        crsi_trigger = connors_rsi_pullback(df, disabled_triggers=disabled_config)
        
        passed_bb = bb_trigger.get("passed", False)
        passed_ma = ma_trigger.get("passed", False)
        passed_dc = dc_trigger.get("passed", False)
        passed_crsi = crsi_trigger.get("passed", False)
        
        if not passed_bb and not passed_ma and not passed_dc and not passed_crsi:
            continue
            
        # Determine trigger type string for final output
        active_triggers = []
        watchlist_triggers = []
        
        if passed_bb:
            if "bollinger_breakout" in active_config:
                active_triggers.append("Bollinger Breakout")
            elif "bollinger_breakout" in watchlist_config:
                watchlist_triggers.append("Bollinger Breakout")
                
        if passed_dc:
            if "donchian_breakout" in active_config:
                active_triggers.append("Donchian Breakout")
            elif "donchian_breakout" in watchlist_config:
                watchlist_triggers.append("Donchian Breakout")
                
        if passed_crsi:
            if "connors_rsi_pullback" in active_config:
                active_triggers.append("ConnorsRSI Pullback")
            elif "connors_rsi_pullback" in watchlist_config:
                watchlist_triggers.append("ConnorsRSI Pullback")
                
        if passed_ma:
            ma_type = ma_trigger.get('reversal_type')
            if ma_type:
                ma_key = ma_type.lower().replace(" ", "_")
                if ma_key in active_config:
                    active_triggers.append(ma_type)
                elif ma_key in watchlist_config:
                    watchlist_triggers.append(ma_type)
            else:
                active_triggers.append("MA Bounce")
                
        if not active_triggers and not watchlist_triggers:
            continue
        
        # Enrich with Fibonacci Confluence
        import pandas as pd
        historical_df = df.loc[df.index <= pd.Timestamp(as_of_date)]
        if not historical_df.empty:
            trigger_high = historical_df['High'].iloc[-1]
            trigger_low = historical_df['Low'].iloc[-1]
        else:
            trigger_high, trigger_low = 0, 0
            
        fib_metrics = get_golden_pocket(historical_df, as_of_date=as_of_date, min_swing_pct=config.FIB_MIN_SWING_PCT)
        
        in_golden_pocket = False
        if fib_metrics:
            p_high = fib_metrics["pocket_high"]
            p_low = fib_metrics["pocket_low"]
            if trigger_low <= p_high and trigger_high >= p_low:
                in_golden_pocket = True
            fib_metrics["in_golden_pocket"] = in_golden_pocket
        else:
            fib_metrics = {"in_golden_pocket": False}
        
        # Compute Relative Strength Score for this symbol
        rs_score = compute_relative_strength(df)
        
        # 6. Build Composite Score
        if active_triggers:
            trigger_type_str = " + ".join(active_triggers)
            score = 0.0
            
            # Base Points per trigger
            if "Bollinger Breakout" in active_triggers: 
                score += 1.0
            if "Donchian Breakout" in active_triggers:
                score += 2.0  # High conviction breakout
            if "ConnorsRSI Pullback" in active_triggers:
                score += 2.5  # High win-rate pullback
            if "Bullish Engulfing" in active_triggers: 
                score += 3.0
            if "Morning Star" in active_triggers:
                score += 1.5
            if "MA Bounce" in active_triggers:
                score += 1.0
            
            # Multi-trigger confluence bonus
            if len(active_triggers) >= 2:
                score += 1.5  # Bonus for multiple triggers firing simultaneously
            
            # Confluence Bonus (Fibonacci)
            if in_golden_pocket:
                gp_scoring = getattr(config, 'GOLDEN_POCKET_SCORING_ENABLED', {})
                if isinstance(gp_scoring, dict) and gp_scoring.get(base_regime, False):
                    score += config.FIB_CONFLUENCE_BONUS
                trigger_type_str += " (Golden Pocket Bounce)"
                
            # Trend Quality Bonuses
            trend_up_days = trend_metrics.get("trend_up_days", 0)
            if trend_up_days > 40:
                score += 1.0
            elif trend_up_days > 20:
                score += 0.5
                
            atr_ratio = trend_metrics.get("atr_ratio", 1.0)
            if atr_ratio < 0.5:
                score += 1.0
            elif atr_ratio < 0.75:
                score += 0.5
                
            # Relative Strength Bonus (top momentum stocks get extra points)
            if rs_score > 0.30:      # > 30% return in 6 months
                score += 2.0
            elif rs_score > 0.15:    # > 15% return
                score += 1.0
            elif rs_score > 0.05:    # > 5% return
                score += 0.5
                
            # --- Dynamic Target & Stop Loss Calculation ---
            high_low = historical_df['High'] - historical_df['Low']
            high_close = np.abs(historical_df['High'] - historical_df['Close'].shift())
            low_close = np.abs(historical_df['Low'] - historical_df['Close'].shift())
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = np.max(ranges, axis=1)
            atr_22 = true_range.rolling(config.CHANDELIER_ATR_PERIOD).mean().iloc[-1]
            
            entry_price = historical_df['Close'].iloc[-1]
            highest_high = historical_df['High'].iloc[-1]
            
            if pd.notna(atr_22) and atr_22 > 0:
                stop_loss = highest_high - (config.CHANDELIER_ATR_MULT * atr_22)
                if stop_loss >= entry_price:
                    stop_loss = entry_price - atr_22
                risk = entry_price - stop_loss
                target = entry_price + (config.RISK_REWARD_RATIO * risk)
            else:
                stop_loss = entry_price * (1 - config.FALLBACK_SL_PCT)
                target = entry_price * (1 + config.FALLBACK_TARGET_PCT)
                
            # Compile candidate
            final_candidates.append({
                "symbol": symbol,
                "trigger_type": trigger_type_str,
                "score": round(score, 2),
                "trend_status": f"{trend_up_days} Days UP",
                "entry_price": round(entry_price, 2),
                "target": round(target, 2),
                "stop_loss": round(stop_loss, 2),
                "rs_rank": round(rs_score * 100, 1),  # As percentage
                "metrics": {
                    "trend_up_days": trend_up_days,
                    "atr_ratio": round(atr_ratio, 2) if atr_ratio else None,
                    "pct_from_high": round(trend_metrics.get("pct_from_high", 0), 3),
                    "rs_6m_return": round(rs_score * 100, 1),
                    "bb_breakout": bb_trigger,
                    "ma_bounce": ma_trigger,
                    "donchian_breakout": dc_trigger,
                    "connors_rsi": crsi_trigger,
                    "fibonacci": fib_metrics
                }
            })
            
        if watchlist_triggers:
            watchlist_type_str = " + ".join(watchlist_triggers)
            if in_golden_pocket:
                watchlist_type_str += " (Golden Pocket Bounce)"
            watchlist_candidates.append({
                "symbol": symbol,
                "trigger_type": watchlist_type_str,
                "metrics": {
                    "bb_breakout": bb_trigger,
                    "ma_bounce": ma_trigger,
                    "fibonacci": fib_metrics
                }
            })
        
    final_count = len(final_candidates)
    logger.info(f"Stage 2 (Trigger Layer) Survivors: {final_count} symbols.")
    
    # 7. Sort by score descending and return top N
    final_candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = final_candidates[:top_n]
    
    # 8. Enrich top candidates with 5-Year Historical Backtest
    if top_candidates:
        logger.info(f"Running 5-Year historical backtest for top {len(top_candidates)} candidates...")
        from src.screener.pipeline.backtest import run_backtest
        for cand in top_candidates:
            try:
                bt_results = run_backtest(months=60, symbols=[cand["symbol"]], return_json=True)
                cand["metrics"]["backtest"] = bt_results.get("metrics", {})
            except Exception as e:
                logger.error(f"Failed to backtest {cand['symbol']}: {e}")
                cand["metrics"]["backtest"] = {}
    
    # Log funnel summary
    logger.info("=========================================")
    logger.info("           SCREENER FUNNEL SUMMARY       ")
    logger.info("=========================================")
    logger.info(f"Initial Universe:     {initial_count}")
    logger.info(f"Liquidity Filter:     {liquidity_count}")
    logger.info(f"Stage 1 (VCP Trend):  {stage1_count}")
    logger.info(f"Stage 1.5 (Fundmnt):  {stage1_5_count}")
    logger.info(f"Stage 2 (Triggers):   {len(final_candidates)}")
    logger.info("=========================================")
    
    if not dry_run:
        logger.info(f"Top {len(top_candidates)} Candidates:")
        for rank, cand in enumerate(top_candidates, 1):
            logger.info(f"#{rank} {cand['symbol']} - Score: {cand['score']} - Trigger: {cand['trigger_type']}")
            
        if watchlist_candidates:
            watchlist_file = f"watchlist_{as_of_date}.txt"
            try:
                with open(watchlist_file, "w") as f:
                    f.write(f"Watchlist Candidates for {as_of_date}\n")
                    f.write("="*40 + "\n")
                    for cand in watchlist_candidates:
                        f.write(f"- {cand['symbol']} ({cand['trigger_type']})\n")
                logger.info(f"Saved {len(watchlist_candidates)} watchlist candidates to {watchlist_file}")
            except Exception as e:
                logger.error(f"Failed to write watchlist file: {e}")
            
    return {
        "candidates": top_candidates,
        "watchlist": watchlist_candidates,
        "regime": current_regime
    }

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the quantitative screening pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Print funnel counts without executing trades/outputs.")
    parser.add_argument("--top", type=int, default=5, help="Number of top candidates to return.")
    parser.add_argument("--regime-check", action="store_true", help="Check and print current market regime before screening.")
    
    args = parser.parse_args()
    
    results = run_screener(dry_run=args.dry_run, top_n=args.top, check_regime=args.regime_check)
    # Print if dry run or directly invoked
    if not args.dry_run:
        pass # Logging already handled inside
