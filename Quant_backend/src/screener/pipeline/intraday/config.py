"""
Configuration for the Intraday ORB & Stocks-in-Play Strategy.
All parameters should be defined here, never hardcoded in the logic.
"""

STRATEGY_CONFIG = {
    # Universe & Liquidity
    "universe": "NIFTY_100",  # Options: NIFTY_50, NIFTY_100, NIFTY_200, NIFTY_500
    "min_avg_traded_value_cr": 50,  # Minimum average daily traded value in Crores
    
    # Gap Parameters
    "min_gap_pct": 0.5,       # Minimum absolute gap % to score points
    
    # RVOL (Time-of-Day Adjusted Relative Volume)
    "rvol_lookback_days": 20, # Historical days to average cumulative volume
    "rvol_threshold_1": 1.5,  # Threshold for +2 points
    "rvol_threshold_2": 2.0,  # Threshold for +3 points
    
    # Opening Range (OR)
    "or_start_time": "09:15",
    "or_end_time": "09:30",
    "execution_timeframe": "5m", # We use 5m candles
    "max_or_width_pct": 2.5,  # Filter out extremely wide opening ranges
    
    # Entry Timing
    "entry_start": "09:30",
    "entry_end": "11:00",
    
    # Risk Management & Stop Loss
    "stop_loss_method": "orb_extremes",  # "orb_extremes" (ORL/ORH) or "atr"
    "atr_multiplier": 1.0,
    "min_rr": 1.5,            # Minimum Risk:Reward ratio required to trade
    
    # Target / Take Profit
    "target_r_multiple": 2.0,
    
    # Position Sizing
    "max_positions": 3,
    "max_trades_per_day": 5,
    "risk_per_trade_pct": 0.01,  # 1% of capital per trade
    "starting_capital": 100000.0,
    
    # Transaction Costs (Indian Markets Equity Intraday MIS)
    "brokerage_pct": 0.0003,      # 0.03% or Rs 20 (we use % for simplicity)
    "stt_pct": 0.00025,           # 0.025% on sell side only
    "exchange_txn_charge_pct": 0.0000325, # NSE charges
    "slippage_pct": 0.0005        # 0.05% slippage on entry and exit
}

# Sector Mappings (Map stock symbols to NSE Sector Indices)
# This allows us to check if the stock's sector is also breaking out.
SECTOR_MAPPING = {
    # IT
    "TCS": "NIFTY_IT", "INFY": "NIFTY_IT", "WIPRO": "NIFTY_IT", "HCLTECH": "NIFTY_IT", "TECHM": "NIFTY_IT", "LTIM": "NIFTY_IT",
    # Bank
    "HDFCBANK": "NIFTY_BANK", "ICICIBANK": "NIFTY_BANK", "SBIN": "NIFTY_BANK", "KOTAKBANK": "NIFTY_BANK", "AXISBANK": "NIFTY_BANK", "INDUSINDBK": "NIFTY_BANK",
    # Auto
    "TATAMOTORS": "NIFTY_AUTO", "M&M": "NIFTY_AUTO", "MARUTI": "NIFTY_AUTO", "BAJAJ-AUTO": "NIFTY_AUTO", "HEROMOTOCO": "NIFTY_AUTO", "EICHERMOT": "NIFTY_AUTO",
    # FMCG
    "ITC": "NIFTY_FMCG", "HUL": "NIFTY_FMCG", "NESTLEIND": "NIFTY_FMCG", "BRITANNIA": "NIFTY_FMCG", "TATACONSUM": "NIFTY_FMCG",
    # Pharma
    "SUNPHARMA": "NIFTY_PHARMA", "CIPLA": "NIFTY_PHARMA", "DRREDDY": "NIFTY_PHARMA", "DIVISLAB": "NIFTY_PHARMA",
    # Metals
    "TATASTEEL": "NIFTY_METAL", "HINDALCO": "NIFTY_METAL", "JSWSTEEL": "NIFTY_METAL", "COALINDIA": "NIFTY_METAL"
}
