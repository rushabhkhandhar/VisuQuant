import pandas as pd
from src.screener import config


def compute_relative_strength(df: pd.DataFrame) -> float:
    """
    Compute the 6-month Relative Strength score for a single stock.
    
    Uses the standard institutional momentum formula:
      RS = (Close_today / Close_N_months_ago) - 1
      BUT skips the most recent month to avoid short-term mean reversion.
    
    This is the exact methodology used by quantitative momentum funds globally
    (Gary Antonacci's Dual Momentum, AQR Capital, etc.)
    
    Returns: float between -1.0 and +inf (percentage return as decimal)
    """
    lookback = config.RS_LOOKBACK_DAYS
    skip = config.RS_SKIP_RECENT_DAYS
    
    # Need at least lookback days of data
    if df.empty or len(df) < lookback + 5:
        return float('-inf')  # Not enough data → worst rank
    
    # Price from ~6 months ago
    close_old = df['Close'].iloc[-(lookback + 1)]
    
    # Price from ~1 month ago (skip recent month to avoid mean reversion)
    close_recent = df['Close'].iloc[-(skip + 1)]
    
    if close_old <= 0:
        return float('-inf')
    
    # Return over the lookback period, excluding the most recent month
    rs_score = (close_recent / close_old) - 1.0
    
    return float(rs_score)


def rank_by_relative_strength(candidates: dict) -> list:
    """
    Takes a dict of {symbol: dataframe} and returns a sorted list of
    (symbol, rs_score) tuples, ranked from highest RS to lowest.
    
    This is applied AFTER Stage 1 to rank the survivors by momentum quality.
    """
    scores = []
    
    for symbol, df in candidates.items():
        rs = compute_relative_strength(df)
        scores.append((symbol, rs))
    
    # Sort descending by RS score
    scores.sort(key=lambda x: x[1], reverse=True)
    
    return scores


def filter_top_rs(candidates: dict, top_pct: float = None) -> list:
    """
    Filter candidates to keep only the top N% by Relative Strength.
    
    Args:
        candidates: dict of {symbol: dataframe}
        top_pct: percentage to keep (default: config.RS_TOP_PCT)
        
    Returns: list of symbols that make the RS cut
    """
    if top_pct is None:
        top_pct = config.RS_TOP_PCT
    
    ranked = rank_by_relative_strength(candidates)
    
    if not ranked:
        return []
    
    # Keep top N%
    n_keep = max(1, int(len(ranked) * (top_pct / 100.0)))
    top_symbols = [symbol for symbol, score in ranked[:n_keep]]
    
    return top_symbols
