import random
import time

def fetch_nse_data(ticker: str) -> dict:
    """
    Mock function representing live market data fetch.
    Replace or extend this with logic from nse_fetcher.py later.
    """
    print(f"[{ticker}] Scraping live NSE data...")
    time.sleep(1) # simulate network latency
    
    # Mock data representing a typical stock's live metrics
    base_price = random.uniform(100.0, 3000.0)
    mock_data = {
        "ticker": ticker,
        "last_price": round(base_price, 2),
        "vwap": round(base_price * random.uniform(0.98, 1.02), 2),
        "volume": random.randint(100000, 5000000),
        "day_high": round(base_price * random.uniform(1.0, 1.05), 2),
        "day_low": round(base_price * random.uniform(0.95, 1.0), 2),
    }
    print(f"[{ticker}] Scraping complete: {mock_data}")
    return mock_data
