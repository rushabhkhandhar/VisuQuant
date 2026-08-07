# Configuration for Quantitative Screener

# Universe Definitions
# List of symbols to scan, or function references (e.g. load_nifty500_symbols)
UNIVERSE = "NIFTY500"

# --- Pipeline Execution Flags ---
STAGE1_FILTER_ENABLED = True      # If True, heavily filters for Stage 2 uptrends & ATR contraction before looking for triggers
DEDUP_WINDOW_DAYS = 10            # Number of trading days before the same trigger can fire again for a symbol

# --- Strategy Thresholds ---
ROUND_TRIP_COST_PCT = 0.002       # 0.2% round-trip cost (brokerage, STT, slippage)

# Liquidity & Volume
LIQUIDITY_MIN_VALUE_CR = 50       # Minimum daily traded value in Crores
VOLUME_BREAKOUT_MULT = 2.5        # Multiplier for volume breakout against average

# Volatility / Range (ATR)
ATR_SHORT = 10                    # Short-term ATR lookback (days)
ATR_LONG = 50                     # Long-term ATR lookback (days)
ATR_CONTRACTION_PERCENTILE = 30   # Keep bottom Nth percentile of ATR ratios (cross-sectional)

# Price Action / Momentum
NEAR_52W_HIGH_PCT = 0.20          # Max percentage distance from 52-week high
BB_LOOKBACK_MONTHS = 6            # Lookback for Bollinger Band squeeze (months)
