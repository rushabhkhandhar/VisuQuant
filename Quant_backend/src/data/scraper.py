from datetime import date, datetime
from src.data.nse_fetcher import fetch_daily_candles, fetch_bulk_history
from src.screener import config

def fetch_nse_data(ticker: str, as_of_date: str = None) -> dict:
    """
    Fetches the most recent daily market data for the given ticker using nse_fetcher.
    Includes historical data for robust technical indicator calculation.
    """
    print(f"[{ticker}] Scraping live NSE data (as_of_date: {as_of_date or 'today'})...")
    
    df = None
    # 1. Primary: Fast, cloud-safe TradingView feed (zero NSE IP blocking)
    try:
        from src.data.live_tv_fetcher import get_tv_fetcher
        fetcher = get_tv_fetcher()
        df = fetcher.fetch_symbol(ticker, n_bars=300)
        if df is not None and not df.empty and as_of_date:
            import pandas as pd
            df = df.loc[df.index <= pd.Timestamp(as_of_date)]
    except Exception as e:
        print(f"[{ticker}] TradingView fetch failed ({e}). Trying Bhavcopy...")

    # 2. Fallback: NSE Bhavcopy archive
    if df is None or df.empty:
        try:
            if as_of_date and as_of_date != date.today().strftime("%Y-%m-%d"):
                target_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
                bulk_data = fetch_bulk_history([ticker], target_date, lookback_days=365)
                df = bulk_data.get(ticker)
                if df is not None and not df.empty:
                    import pandas as pd
                    df = df.loc[df.index <= pd.Timestamp(target_date)]
            else:
                df = fetch_daily_candles(ticker, date.today(), lookback_days=365)
        except Exception as e:
            print(f"[{ticker}] NSE Bhavcopy fallback failed: {e}")

    if df is not None and not df.empty:
        latest = df.iloc[-1]
        
        # Format history properly (convert timestamps to string if any)
        df_history = df.reset_index()
        if 'Date' in df_history.columns:
            df_history['Date'] = df_history['Date'].astype(str)
            
        import pandas as pd
        import numpy as np
        
        # Calculate ATR(22) for Target and Stop Loss
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        ranges = pd.concat([high_low, high_close, low_close], axis=1)
        true_range = np.max(ranges, axis=1)
        atr_22 = true_range.rolling(config.CHANDELIER_ATR_PERIOD).mean().iloc[-1]
        
        entry_price = latest['Close']
        highest_high = latest['High']
        
        if pd.notna(atr_22) and atr_22 > 0:
            stop_loss = highest_high - (config.CHANDELIER_ATR_MULT * atr_22)
            if stop_loss >= entry_price:
                stop_loss = entry_price - atr_22
            risk = entry_price - stop_loss
            target = entry_price + (config.RISK_REWARD_RATIO * risk)
        else:
            stop_loss = entry_price * (1 - config.FALLBACK_SL_PCT)
            target = entry_price * (1 + config.FALLBACK_TARGET_PCT)
        
        # Compute VWAP only if column exists in the data
        vwap_val = float(latest['VWAP']) if 'VWAP' in df.columns and pd.notna(latest.get('VWAP')) else None
        
        data = {
            "ticker": ticker,
            "current_price": float(latest['Close']),
            "last_price": float(latest['Close']),  # Backward compat alias
            "day_high": float(latest['High']),
            "day_low": float(latest['Low']),
            "vwap": vwap_val,
            "volume": int(latest['Volume']),
            "entry_price": float(entry_price),
            "target": float(target),
            "stop_loss": float(stop_loss),
            "history": df_history.tail(50).to_dict(orient="records")
        }
        
        print(f"[{ticker}] Scraping complete with {len(df)} historical candles.")
        return data
    else:
        raise ValueError(f"Failed to fetch actual data from NSE for ticker {ticker}")
