from datetime import date
from src.data.nse_fetcher import fetch_bulk_history

def filter_by_liquidity(universe: list[str], min_value_cr: float, as_of_date: date = None) -> list[str]:
    """
    Computes 20-day average daily traded value (Close * Volume) per stock.
    Drops anything below min_value_cr (in ₹ Crore).
    """
    if as_of_date is None:
        as_of_date = date.today()
        
    # We need 20 trading days, fetch 35 calendar days to safely cover weekends/holidays
    bulk_data = fetch_bulk_history(universe, as_of_date, lookback_days=35)
    
    passed_symbols = []
    for symbol, df in bulk_data.items():
        if df.empty or len(df) < 20:
            continue
            
        # Extract the last 20 trading days
        df_20d = df.tail(20)
        
        # Calculate daily traded value in Crores
        # NSE Volume is number of shares, Price is INR. 
        # Value = (Close * Volume) / 10_000_000 to get Crores
        daily_value_cr = (df_20d['Close'] * df_20d['Volume']) / 10_000_000
        
        avg_20d_value = daily_value_cr.mean()
        
        if avg_20d_value >= min_value_cr:
            passed_symbols.append(symbol)
            
    return passed_symbols
