import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from datetime import date
from src.nse_fetcher import fetch_daily_candles

def main():
    symbol = "RELIANCE"
    print(f"Fetching recent data for {symbol} using nse_fetcher.py...")
    # Fetch data for the last 20 days
    df = fetch_daily_candles(symbol, date.today(), lookback_days=20)
    
    if df is not None and not df.empty:
        print("\nFetched Data:")
        print(df)
        csv_path = f"{symbol}_recent_data.csv"
        df.to_csv(csv_path)
        print(f"\nSaved data to {csv_path}")
    else:
        print("\nFailed to fetch data or no data returned.")

if __name__ == "__main__":
    main()
