# Configuration for Quantitative Screener

# Universe Definitions
# List of symbols to scan, or function references (e.g. load_nifty500_symbols)
UNIVERSE = "NIFTY500"

# --- Pipeline Execution Flags ---
STAGE1_FILTER_ENABLED = True      # If True, heavily filters for Stage 2 uptrends & ATR contraction before looking for triggers
DEDUP_WINDOW_DAYS = 10            # Number of trading days before the same trigger can fire again for a symbol

# --- Dynamic Regime Trigger Configuration ---
REGIME_STRATEGIES = {
    "TRENDING UP": {
        "active": ["bollinger_breakout", "bullish_engulfing"],
        "watchlist": ["morning_star"],
        "disabled": ["hammer"]
    },
    "TRENDING DOWN": {
        "active": ["hammer"], # Look for deep oversold bounce/capitulation
        "watchlist": ["bullish_engulfing"],
        "disabled": ["bollinger_breakout", "morning_star"]
    },
    "CHOPPY": {
        "active": ["morning_star"], # Mean reversion
        "watchlist": ["bollinger_breakout", "bullish_engulfing"],
        "disabled": ["hammer"]
    }
}

GOLDEN_POCKET_SCORING_ENABLED = {
    "TRENDING UP": False,
    "TRENDING DOWN": False,
    "CHOPPY": True
}

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

# Fibonacci Confluence
FIB_CONFLUENCE_BONUS = 0.1        # Additive bonus to composite score if in golden pocket
FIB_MIN_SWING_PCT = 8.0           # Minimum swing magnitude % to be considered for fib retracement

# --- Chandelier Exit / Trade Execution Parameters ---
CHANDELIER_ATR_PERIOD = 22        # ATR period for Chandelier Exit
CHANDELIER_ATR_MULT = 3.0         # ATR multiplier for trailing stop (Highest High - MULT * ATR)
RISK_REWARD_RATIO = 2.0           # Risk-to-Reward ratio for target calculation (Target = Entry + RR * Risk)
FALLBACK_SL_PCT = 0.05            # 5% fallback stop-loss when ATR is unavailable
FALLBACK_TARGET_PCT = 0.10        # 10% fallback target when ATR is unavailable

# --- Volatility Classification Thresholds ---
VOLATILITY_LOW_ATR_PCT = 1.0      # ATR% below this → "Low" volatility
VOLATILITY_HIGH_ATR_PCT = 3.0     # ATR% above this → "High" volatility

# --- Bollinger Band Interpretation Thresholds ---
BB_SQUEEZE_THRESHOLD = 0.05       # Bandwidth below this → Squeeze detected
BB_WIDE_THRESHOLD = 0.15          # Bandwidth above this → High volatility

# --- Relative Volume Thresholds ---
RELATIVE_VOLUME_HIGH = 1.2        # Above this → Volume expansion
RELATIVE_VOLUME_LOW = 0.8         # Below this → Volume contraction

# --- Institutional Liquidity Filters ---
INSTITUTIONAL_ADV_SHARES = 100000   # Minimum average daily volume (shares)
INSTITUTIONAL_ADV_CURRENCY = 10000000  # Minimum average daily turnover (INR)
