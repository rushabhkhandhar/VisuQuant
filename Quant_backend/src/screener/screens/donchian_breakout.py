import pandas as pd
from src.screener import config


def donchian_breakout(df: pd.DataFrame, disabled_triggers: list = None) -> dict:
    """
    Donchian Channel Breakout (Turtle Trading Style).
    
    Entry signal: Close breaks above the highest High of the last N days.
    Volume confirmation: Breakout volume >= DONCHIAN_VOLUME_MULT * 20-day avg.
    
    This is a much higher-frequency trigger than BB Squeeze because it only
    requires price to make a new N-day high with decent volume — no squeeze needed.
    """
    if disabled_triggers is None:
        disabled_triggers = []
        
    if "donchian_breakout" in disabled_triggers:
        return {"passed": False, "channel_high": None, "channel_low": None, "volume_ratio": None}
        
    period = config.DONCHIAN_ENTRY_PERIOD
    exit_period = config.DONCHIAN_EXIT_PERIOD
    vol_mult = config.DONCHIAN_VOLUME_MULT
    
    # Need enough data for the channel + some buffer
    if df.empty or len(df) < period + 5:
        return {"passed": False, "channel_high": None, "channel_low": None, "volume_ratio": None}
    
    # Donchian Channel: highest High and lowest Low over the lookback
    # IMPORTANT: We use the PREVIOUS period's high (not including today) to avoid lookahead
    # The breakout is: today's Close > highest High of the PREVIOUS N days
    prev_n_highs = df['High'].iloc[-(period + 1):-1]  # Last N days EXCLUDING today
    prev_n_lows = df['Low'].iloc[-(exit_period + 1):-1]
    
    channel_high = prev_n_highs.max()
    channel_low = prev_n_lows.min()
    
    curr_close = df['Close'].iloc[-1]
    curr_volume = df['Volume'].iloc[-1]
    
    # 20-day average volume (excluding today to avoid self-reference)
    avg_vol_20d = df['Volume'].iloc[-21:-1].mean() if len(df) >= 22 else df['Volume'].iloc[:-1].mean()
    
    vol_ratio = curr_volume / avg_vol_20d if avg_vol_20d > 0 else 0
    
    # Condition 1: Close breaks above the channel high
    cond1 = curr_close > channel_high
    
    # Condition 2: Volume confirmation (looser than BB — 1.5x instead of 2.5x)
    cond2 = vol_ratio >= vol_mult
    
    passed = bool(cond1 and cond2)
    
    return {
        "passed": passed,
        "channel_high": float(channel_high),
        "channel_low": float(channel_low),
        "volume_ratio": float(vol_ratio),
        "is_breakout": bool(cond1),
        "is_vol_confirmed": bool(cond2)
    }
