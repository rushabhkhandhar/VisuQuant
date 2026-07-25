from datetime import date
from src.nse_fetcher import fetch_daily_candles

def fetch_nse_data(ticker: str) -> dict:
    """
    Fetches the most recent daily market data for the given ticker using nse_fetcher.
    Includes historical data for robust technical indicator calculation.
    """
    print(f"[{ticker}] Scraping live NSE data...")
    
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
