# Configuration for Quantitative Screener

# Universe Definitions
# List of symbols to scan, or function references (e.g. load_nifty500_symbols)
UNIVERSE = "NIFTY500"

# --- Strategy Thresholds ---

# Liquidity & Volume
LIQUIDITY_MIN_VALUE_CR = 50       # Minimum daily traded value in Crores
VOLUME_BREAKOUT_MULT = 2.5        # Multiplier for volume breakout against average

# Volatility / Range (ATR)
ATR_SHORT = 10                    # Short-term ATR lookback (days)
ATR_LONG = 50                     # Long-term ATR lookback (days)

# Price Action / Momentum
NEAR_52W_HIGH_PCT = 0.20          # Max percentage distance from 52-week high
BB_LOOKBACK_MONTHS = 6            # Lookback for Bollinger Band squeeze (months)
