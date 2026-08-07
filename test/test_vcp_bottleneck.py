import pandas as pd
from src.screener import config
from src.data.nse_fetcher import fetch_bulk_history, load_nifty500_symbols
from src.screener.screens.vcp_trend_template import evaluate_vcp_trend
from src.screener.indicators.core import sma, atr, rolling_52w_high
from datetime import date

symbols = load_nifty500_symbols()
data = fetch_bulk_history(symbols, date.today(), 400)

counts = {"C1_SMA_Stack": 0, "C2_SMA200_Up": 0, "C3_Near_52W": 0, "C4_ATR_Ratio_0.75": 0, "C5_Vol_DryUp": 0, "All_Trend_No_ATR": 0}
total_valid = 0

for sym, df in data.items():
    if len(df) < 200: continue
    total_valid += 1
    
    sma50 = sma(df['Close'], 50).iloc[-1]
    sma150 = sma(df['Close'], 150).iloc[-1]
    sma200 = sma(df['Close'], 200)
    curr_sma200 = sma200.iloc[-1]
    current_close = df['Close'].iloc[-1]
    
    cond1 = (current_close > sma50) and (sma50 > sma150) and (sma150 > curr_sma200)
    
    sma200_diff = sma200.diff().tail(60).values
    trend_up_days = 0
    for val in reversed(sma200_diff):
        if val > 0:
            trend_up_days += 1
        else:
            break
    cond2 = trend_up_days >= 20
    
    curr_high_52w = rolling_52w_high(df['High']).iloc[-1]
    pct_from_high = (curr_high_52w - current_close) / curr_high_52w
    cond3 = pct_from_high <= config.NEAR_52W_HIGH_PCT
    
    curr_atr10 = atr(df, 10).iloc[-1]
    curr_atr50 = atr(df, 50).iloc[-1]
    atr_ratio = curr_atr10 / curr_atr50 if curr_atr50 > 0 else 1.0
    cond4 = atr_ratio < config.ATR_CONTRACTION_THRESHOLD
    
    prev_close = df['Close'].shift(1)
    is_down_day = df['Close'] < prev_close
    last_10_down_vols = df['Volume'].tail(10)[is_down_day.tail(10)]
    avg_down_vol_10d = last_10_down_vols.mean() if not last_10_down_vols.empty else 0
    avg_vol_20d = df['Volume'].tail(20).mean()
    cond5 = avg_down_vol_10d < avg_vol_20d
    
    if cond1: counts["C1_SMA_Stack"] += 1
    if cond2: counts["C2_SMA200_Up"] += 1
    if cond3: counts["C3_Near_52W"] += 1
    if cond4: counts["C4_ATR_Ratio_0.75"] += 1
    if cond5: counts["C5_Vol_DryUp"] += 1
    
    if cond1 and cond2 and cond3 and cond5:
        counts["All_Trend_No_ATR"] += 1
        
print(f"Total Valid Symbols (>200d history): {total_valid}")
print(f"C1 (Close > 50 > 150 > 200):  {counts['C1_SMA_Stack']} passed")
print(f"C2 (200 SMA Up 20+ days):     {counts['C2_SMA200_Up']} passed")
print(f"C3 (Within 20% of 52W High):  {counts['C3_Near_52W']} passed")
print(f"C4 (ATR Ratio < 0.75):        {counts['C4_ATR_Ratio_0.75']} passed")
print(f"C5 (Down Vol < 20d Avg Vol):  {counts['C5_Vol_DryUp']} passed")
print(f"Passed All TREND (No ATR):    {counts['All_Trend_No_ATR']} passed")

