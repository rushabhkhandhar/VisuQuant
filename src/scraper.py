from datetime import date
from src.nse_fetcher import fetch_daily_candles

def fetch_nse_data(ticker: str) -> dict:
    """
    Fetches the most recent daily market data for the given ticker using nse_fetcher.
    """
    print(f"[{ticker}] Scraping live NSE data...")
    
    # We fetch the last 20 days to ensure we get enough data ignoring weekends/holidays
    df = fetch_daily_candles(ticker, date.today(), lookback_days=20)
    
    if df is not None and not df.empty:
        latest = df.iloc[-1]
        data = {
            "ticker": ticker,
            "last_price": round(latest["Close"], 2),
            "vwap": round((latest["High"] + latest["Low"] + latest["Close"]) / 3, 2), # simple approximation
            "volume": int(latest["Volume"]),
            "day_high": round(latest["High"], 2),
            "day_low": round(latest["Low"], 2),
        }
    else:
        raise ValueError(f"Failed to fetch actual data from NSE for ticker {ticker}")
        
    print(f"[{ticker}] Scraping complete: {data}")
    return data
