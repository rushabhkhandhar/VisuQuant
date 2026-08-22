import pandas as pd
import numpy as np
from datetime import datetime, time as dtime

def calculate_gap(daily_df, today_open):
    """
    Calculate Gap % = ((Today's Open - Previous Close) / Previous Close) * 100
    daily_df should be the completed daily dataframe (excluding today).
    """
    if len(daily_df) == 0:
        return 0.0, 0.0
    
    prev_close = daily_df['Close'].iloc[-1]
    gap_pct = ((today_open - prev_close) / prev_close) * 100.0
    return gap_pct, prev_close

def calculate_or(intraday_df, or_start, or_end):
    """
    Calculate the Opening Range (OR) given a start and end time.
    intraday_df: Today's 5m dataframe.
    or_start/or_end: strings like '09:15', '09:30'
    """
    # TradingView 5m candles are timestamped at the open.
    # 09:15 covers 09:15-09:20.
    # So if or_end is '09:30', we want candles with index time <= 09:25.
    or_df = intraday_df.between_time(or_start, (pd.to_datetime(or_end) - pd.Timedelta(minutes=1)).strftime('%H:%M'))

    if len(or_df) == 0:
        return None
        
    orh = or_df['High'].max()
    orl = or_df['Low'].min()
    or_width = orh - orl
    or_mid = (orh + orl) / 2.0
    or_width_pct = (or_width / or_mid) * 100.0
    
    return {
        "orh": orh,
        "orl": orl,
        "or_width": or_width,
        "or_width_pct": or_width_pct,
        "or_volume": or_df['Volume'].sum()
    }

def calculate_vwap(intraday_df):
    """
    Calculate daily resetting intraday VWAP.
    Adds 'VWAP' column to the dataframe.
    """
    df = intraday_df.copy()
    
    # Calculate Typical Price
    df['TP'] = (df['High'] + df['Low'] + df['Close']) / 3
    df['TPV'] = df['TP'] * df['Volume']
    
    # Daily cumsum
    df['cum_TPV'] = df.groupby(df.index.date)['TPV'].cumsum()
    df['cum_Vol'] = df.groupby(df.index.date)['Volume'].cumsum()
    
    df['VWAP'] = df['cum_TPV'] / df['cum_Vol']
    
    # Calculate VWAP Slope (change over last 3 candles)
    df['VWAP_Slope'] = df['VWAP'].diff(3)
    
    return df

def calculate_time_of_day_rvol(full_intraday_df, current_time, lookback_days=20):
    """
    Calculate time-of-day adjusted RVOL.
    Compares today's cumulative volume up to current_time 
    against historical average cumulative volume up to current_time.
    """
    if full_intraday_df.empty:
        return 0.0, 0.0, 0.0
        
    current_date = full_intraday_df.index[-1].date()
    
    # Get all historical days (excluding today)
    historical_df = full_intraday_df[full_intraday_df.index.date < current_date]
    if len(historical_df) == 0:
        return 0.0, 0.0, 0.0
        
    unique_dates = pd.Series(historical_df.index.date).unique()[-lookback_days:]
    
    hist_cum_vols = []
    for d in unique_dates:
        day_df = historical_df[historical_df.index.date == d]
        day_up_to_t = day_df.between_time('09:15', current_time)
        hist_cum_vols.append(day_up_to_t['Volume'].sum())
        
    avg_hist_vol = np.mean(hist_cum_vols) if hist_cum_vols else 0.0
    
    today_df = full_intraday_df[full_intraday_df.index.date == current_date]
    today_up_to_t = today_df.between_time('09:15', current_time)
    today_vol = today_up_to_t['Volume'].sum()
    
    if avg_hist_vol == 0:
        return 0.0, today_vol, avg_hist_vol
        
    rvol = today_vol / avg_hist_vol
    return rvol, today_vol, avg_hist_vol

def precompute_historical_rvol(full_intraday_df, current_date, lookback_days=20):
    """
    Precomputes the historical average cumulative volume up to every 5-minute interval.
    Returns a dictionary mapping 'HH:MM' string to average volume.
    """
    historical_df = full_intraday_df[full_intraday_df.index.date < current_date]
    if len(historical_df) == 0:
        return {}
        
    unique_dates = pd.Series(historical_df.index.date).unique()[-lookback_days:]
    historical_df = historical_df[np.isin(historical_df.index.date, unique_dates)]
    
    # Calculate cumulative volume for each day
    historical_df['cum_vol'] = historical_df.groupby(historical_df.index.date)['Volume'].cumsum()
    
    # Group by time and average the cumulative volume across days
    historical_df['time_str'] = historical_df.index.strftime('%H:%M')
    avg_vols = historical_df.groupby('time_str')['cum_vol'].mean().to_dict()
    
    return avg_vols

def calculate_fast_rvol(today_df_up_to_t, current_time, precomputed_vols):
    """
    Fast O(1) version using precomputed averages.
    """
    avg_hist_vol = precomputed_vols.get(current_time, 0.0)
    today_vol = today_df_up_to_t['Volume'].sum()
    
    if avg_hist_vol == 0:
        return 0.0, today_vol, avg_hist_vol
        
    rvol = today_vol / avg_hist_vol
    return rvol, today_vol, avg_hist_vol

def calculate_relative_strength(stock_df, nifty_df):
    """
    Relative Strength since Open.
    Both dataframes should be filtered to today's data up to current_time.
    """
    if len(stock_df) == 0 or len(nifty_df) == 0:
        return 0.0
        
    stock_open = stock_df['Open'].iloc[0]
    stock_current = stock_df['Close'].iloc[-1]
    stock_ret = (stock_current - stock_open) / stock_open * 100.0
    
    nifty_open = nifty_df['Open'].iloc[0]
    nifty_current = nifty_df['Close'].iloc[-1]
    nifty_ret = (nifty_current - nifty_open) / nifty_open * 100.0
    
    rs = stock_ret - nifty_ret
    return rs

def calculate_atr(daily_df, period=14):
    """
    Calculate Average True Range (ATR).
    """
    if len(daily_df) < period + 1:
        return 0.0
        
    df = daily_df.copy()
    df['prev_close'] = df['Close'].shift(1)
    df['tr1'] = df['High'] - df['Low']
    df['tr2'] = (df['High'] - df['prev_close']).abs()
    df['tr3'] = (df['Low'] - df['prev_close']).abs()
    df['tr'] = df[['tr1', 'tr2', 'tr3']].max(axis=1)
    
    atr = df['tr'].rolling(window=period).mean().iloc[-1]
    return atr
