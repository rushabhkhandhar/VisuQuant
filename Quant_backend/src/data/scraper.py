from datetime import date, datetime
from src.data.nse_fetcher import fetch_daily_candles, fetch_bulk_history

def fetch_nse_data(ticker: str, as_of_date: str = None) -> dict:
    """
    Fetches the most recent daily market data for the given ticker using nse_fetcher.
    Includes historical data for robust technical indicator calculation.
    """
    print(f"[{ticker}] Scraping live NSE data (as_of_date: {as_of_date or 'today'})...")
    
    if as_of_date and as_of_date != date.today().strftime("%Y-%m-%d"):
        target_date = datetime.strptime(as_of_date, "%Y-%m-%d").date()
        # For historical runs, use bulk fetcher to get exact historical state
        bulk_data = fetch_bulk_history([ticker], target_date, lookback_days=365)
        df = bulk_data.get(ticker)
        if df is not None and not df.empty:
            import pandas as pd
            df = df.loc[df.index <= pd.Timestamp(target_date)]
    else:
        # We fetch the last 365 days to ensure we get enough data for 200-day EMA and 52-week High/Low
        df = fetch_daily_candles(ticker, date.today(), lookback_days=365)
    
    if df is not None and not df.empty:
        latest = df.iloc[-1]
        
        # Format history properly (convert timestamps to string if any)
        df_history = df.reset_index()
        if 'Date' in df_history.columns:
            df_history['Date'] = df_history['Date'].astype(str)
            
        data = {
            "ticker": ticker,
            "last_price": round(latest["Close"], 2),
            "vwap": round((latest["High"] + latest["Low"] + latest["Close"]) / 3, 2), # simple approximation
            "volume": int(latest["Volume"]),
            "day_high": round(latest["High"], 2),
            "day_low": round(latest["Low"], 2),
            "history": df_history.to_dict(orient="records")
        }
    else:
        raise ValueError(f"Failed to fetch actual data from NSE for ticker {ticker}")
        
    print(f"[{ticker}] Scraping complete with {len(df)} historical candles.")
    return data
