# Configuration for Quantitative Screener

# Universe Definitions
UNIVERSE = "NIFTY500"

# --- Pipeline Execution Flags ---
STAGE1_FILTER_ENABLED = True      # If True, heavily filters for Stage 2 uptrends & ATR contraction before looking for triggers
DEDUP_WINDOW_DAYS = 10            # Number of trading days before the same trigger can fire again for a symbol

# --- Dynamic Regime Trigger Configuration ---
# Each trigger can be "active" (scores for ranking), "watchlist" (flagged only), or "disabled"
REGIME_STRATEGIES = {
    "TRENDING UP": {
        "active": ["donchian_breakout", "connors_rsi_pullback", "bollinger_breakout", "bullish_engulfing"],
        "watchlist": ["morning_star"],
        "disabled": ["hammer"]
    },
    "TRENDING DOWN": {
        "active": ["hammer"],
        "watchlist": ["connors_rsi_pullback", "bullish_engulfing"],
        "disabled": ["bollinger_breakout", "morning_star", "donchian_breakout"]
    },
    "CHOPPY": {
        "active": ["connors_rsi_pullback", "morning_star"],
        "watchlist": ["bollinger_breakout", "bullish_engulfing"],
        "disabled": ["hammer", "donchian_breakout"]
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
RISK_REWARD_RATIO = 2.0           # Risk-to-Reward ratio for target calculation
FALLBACK_SL_PCT = 0.05            # 5% fallback stop-loss when ATR is unavailable
FALLBACK_TARGET_PCT = 0.10        # 10% fallback target when ATR is unavailable

# --- Volatility Classification Thresholds ---
VOLATILITY_LOW_ATR_PCT = 1.0
VOLATILITY_HIGH_ATR_PCT = 3.0

# --- Bollinger Band Interpretation Thresholds ---
BB_SQUEEZE_THRESHOLD = 0.05
BB_WIDE_THRESHOLD = 0.15

# --- Relative Volume Thresholds ---
RELATIVE_VOLUME_HIGH = 1.2
RELATIVE_VOLUME_LOW = 0.8

# --- Institutional Liquidity Filters ---
INSTITUTIONAL_ADV_SHARES = 100000
INSTITUTIONAL_ADV_CURRENCY = 10000000

# ===================================================================
# NEW STRATEGY PARAMETERS
# ===================================================================

# --- Donchian Channel Breakout (Turtle Trading) ---
DONCHIAN_ENTRY_PERIOD = 20        # Buy when Close > highest High of last N days
DONCHIAN_EXIT_PERIOD = 10         # Exit when Close < lowest Low of last N days
DONCHIAN_VOLUME_MULT = 1.5        # Volume must be >= this * 20-day avg (looser than BB)

# --- ConnorsRSI Pullback ---
CONNORS_RSI_PERIOD = 3            # Ultra-short RSI period for mean-reversion
CONNORS_STREAK_PERIOD = 2         # Streak length for up/down day counting
CONNORS_PCTRANK_PERIOD = 100      # Percentile rank lookback
CONNORS_RSI_OVERSOLD = 10         # ConnorsRSI below this = oversold pullback signal
CONNORS_RSI_OVERBOUGHT = 90       # ConnorsRSI above this = overbought (for exits)
CONNORS_MAX_HOLD_DAYS = 5         # Time-based exit: close after N days if no target/SL hit

# --- Relative Strength Ranking ---
RS_LOOKBACK_DAYS = 126            # ~6 months of trading days for momentum calculation
RS_SKIP_RECENT_DAYS = 21          # Skip last ~1 month to avoid short-term mean reversion
RS_TOP_PCT = 20                   # Keep top N% of stocks by RS rank (applied after Stage 1)

# --- Portfolio Risk Management ---
MAX_PORTFOLIO_HEAT_PCT = 6.0      # Max total portfolio risk across all open positions
MAX_SECTOR_CONCENTRATION = 2      # Max stocks from same sector in active positions
