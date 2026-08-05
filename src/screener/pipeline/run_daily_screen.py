import argparse
import logging
from datetime import date
from typing import List, Dict, Any

from src.screener import config
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.screener.screens.liquidity import filter_by_liquidity
from src.screener.screens.vcp_trend_template import evaluate_vcp_trend
from src.screener.screens.trigger_layer import bollinger_squeeze_breakout, ma_pullback_bounce
from src.screener.screens.fib_confluence import score_fib_confluence

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def run_screener(as_of_date: date = None, dry_run: bool = False, top_n: int = 5) -> List[Dict[str, Any]]:
    if as_of_date is None:
        as_of_date = date.today()
        
    logger.info(f"--- Starting Daily Quantitative Screen for {as_of_date} ---")
    
    # 1. Load Universe
    universe = load_nifty500_symbols()
        
    initial_count = len(universe)
    logger.info(f"Loaded initial universe: {initial_count} symbols.")
    
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
    
    # 3. Stage 1: VCP Trend Template
    stage1_survivors = {}
    logger.info("Running Stage 1: Minervini VCP Trend Template...")
    
    for symbol, df in bulk_data.items():
        if df.empty:
            continue
            
        trend_metrics = evaluate_vcp_trend(df, config.NEAR_52W_HIGH_PCT)
        if trend_metrics.get("passed", False):
            stage1_survivors[symbol] = {
                "df": df,
                "trend_metrics": trend_metrics
            }
            
    stage1_count = len(stage1_survivors)
    logger.info(f"Stage 1 (VCP Trend) Survivors: {stage1_count} symbols.")
    
    if stage1_count == 0:
        logger.warning("Pipeline halted: 0 symbols survived Stage 1.")
        return []
        
    # 4 & 5. Stage 2: Trigger Layer & Fib Confluence
    logger.info("Running Stage 2: Trigger Layer (Bollinger Squeeze / MA Pullback)...")
    final_candidates = []
    
    for symbol, data in stage1_survivors.items():
        df = data["df"]
        trend_metrics = data["trend_metrics"]
        
        # Run independent triggers
        bb_trigger = bollinger_squeeze_breakout(df, config.BB_LOOKBACK_MONTHS, config.VOLUME_BREAKOUT_MULT)
        ma_trigger = ma_pullback_bounce(df)
        
        passed_bb = bb_trigger.get("passed", False)
        passed_ma = ma_trigger.get("passed", False)
        
        if not passed_bb and not passed_ma:
            continue
            
        # Determine trigger type string for final output
        trigger_types = []
        if passed_bb: trigger_types.append("Bollinger Breakout")
        if passed_ma: trigger_types.append(f"{ma_trigger.get('reversal_type', 'MA Bounce')}")
        trigger_type_str = " + ".join(trigger_types)
        
        # Enrih with Fibonacci Confluence
        fib_metrics = score_fib_confluence(df)
        
        # 6. Build Composite Score
        score = 0.0
        
        # Base Points
        if passed_bb: score += 2.0
        if passed_ma: score += 2.0
        
        # Confluence Bonus
        if fib_metrics.get("in_golden_pocket", False):
            score += 1.5
            trigger_type_str += " (Golden Pocket Bounce)"
            
        # Trend Quality Bonuses
        trend_up_days = trend_metrics.get("trend_up_days", 0)
        if trend_up_days > 40:
            score += 1.0 # Extra mature trend
        elif trend_up_days > 20:
            score += 0.5
            
        atr_ratio = trend_metrics.get("atr_ratio", 1.0)
        if atr_ratio < 0.5:
            score += 1.0 # Extreme volatility contraction
        elif atr_ratio < 0.75:
            score += 0.5
            
        # Compile candidate
        final_candidates.append({
            "symbol": symbol,
            "trigger_type": trigger_type_str,
            "score": round(score, 2),
            "metrics": {
                "trend_up_days": trend_up_days,
                "atr_ratio": round(atr_ratio, 2) if atr_ratio else None,
                "pct_from_high": round(trend_metrics.get("pct_from_high", 0), 3),
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
    
    # Log funnel summary
    logger.info("=========================================")
    logger.info("           SCREENER FUNNEL SUMMARY       ")
    logger.info("=========================================")
    logger.info(f"Initial Universe:     {initial_count}")
    logger.info(f"Liquidity Filter:     {liquidity_count}")
    logger.info(f"Stage 1 (VCP Trend):  {stage1_count}")
    logger.info(f"Stage 2 (Triggers):   {final_count}")
    logger.info("=========================================")
    
    if not dry_run:
        logger.info(f"Top {len(top_candidates)} Candidates:")
        for rank, cand in enumerate(top_candidates, 1):
            logger.info(f"#{rank} {cand['symbol']} - Score: {cand['score']} - Trigger: {cand['trigger_type']}")
            
    return top_candidates

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run the quantitative screening pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Print funnel counts without executing trades/outputs.")
    parser.add_argument("--top", type=int, default=5, help="Number of top candidates to return.")
    
    args = parser.parse_args()
    
    run_screener(dry_run=args.dry_run, top_n=args.top)
