STRATEGY_CONFIG = {
    # Account Settings
    "starting_capital": 300000.0,   # 1 Lakh
    "risk_per_trade_pct": 0.15,     # Increased to 15% so a 3 Lakh account can afford 1 lot of F&O risk
    
    # Portfolio constraints
    "max_open_positions": 2,       # Only buy top 2 strongest stocks
    
    # Sector & Screener Parameters
    "sector_momentum_lookback": 20, # 1 Month (20 trading days) return to rank sectors
    "top_n_sectors": 2,             # Focus on top 2 sectors
    
    # Trade Management
    "atr_period": 14,
    "atr_stop_loss_multiplier": 1.5, # Stop loss 1.5 ATR below entry
    "target_r_multiple": 1.5,        # 1:1.5 Risk/Reward
    
    # Execution mechanics
    "entry_time": "15:15",         # Simulated entry at EOD
    "margin_requirement_pct": 0.20 # Approx 20% margin required per lot
}
