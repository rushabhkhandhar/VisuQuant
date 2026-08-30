STRATEGY_CONFIG = {
    # Account Settings
    "starting_capital": 5000000.0,   # 1 Lakh
    "risk_per_trade_pct": 0.05,     # Increased to 5% because 1 Lakh is too small for 2% risk on F&O lots
    
    # Portfolio constraints
    "max_open_positions": 2,       # Only short top 2 weakest stocks
    
    # Sector & Screener Parameters
    "sector_momentum_lookback": 20, # 1 Month (20 trading days) return to rank sectors
    "bottom_n_sectors": 2,         # Focus on bottom 2 sectors
    
    # Trade Management
    "atr_period": 14,
    "atr_stop_loss_multiplier": 2.0, # Stop loss 2 ATR above entry
    "target_r_multiple": 2.5,        # 1:2.5 Risk/Reward
    
    # Execution mechanics
    "entry_time": "15:15",         # Simulated entry at EOD
    "margin_requirement_pct": 0.20 # Approx 20% margin required per lot
}
