import os
import time
import json
from datetime import date, datetime, timedelta
from io import StringIO
import logging
from typing import Any, Dict, List, Optional, Sequence
import urllib.error
from urllib.request import Request, urlopen
import pandas as pd
from concurrent.futures import ThreadPoolExecutor

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Global in-memory cache to avoid repeated network requests in the same run
_BHAVCOPY_CACHE: Dict[str, Optional[pd.DataFrame]] = {}

# Persistent on-disk cache to survive script restarts and avoid rate-limiting
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bhavcopy_cache")
os.makedirs(_CACHE_DIR, exist_ok=True)

def cleanup_cache():
    """Delete the disk cache to free up space after execution."""
    import shutil
    try:
        if os.path.exists(_CACHE_DIR):
            shutil.rmtree(_CACHE_DIR)
            print("Successfully deleted NSE bhavcopy cache to save space.")
    except Exception as e:
        print(f"Failed to clear cache: {e}")

def _download_bhavcopy_for_date(trade_date: date) -> Optional[pd.DataFrame]:
    """Download one NSE full bhavcopy day (or load from disk/in-memory cache)."""
    key = trade_date.strftime("%Y-%m-%d")
    
    # 1. Check in-memory
    if key in _BHAVCOPY_CACHE:
        return _BHAVCOPY_CACHE[key]

    disk_path = os.path.join(_CACHE_DIR, f"{key}.parquet")
    missing_path = os.path.join(_CACHE_DIR, f"{key}.missing")

    # 2. Check disk cache
    if os.path.exists(missing_path):
        _BHAVCOPY_CACHE[key] = None
        return None
    if os.path.exists(disk_path):
        try:
            df = pd.read_parquet(disk_path)
            _BHAVCOPY_CACHE[key] = df
            return df
        except Exception:
            pass # Fall back to download if corrupted

    url = (
        "https://nsearchives.nseindia.com/products/content/"
        f"sec_bhavdata_full_{trade_date.strftime('%d%m%Y')}.csv"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Connection": "keep-alive"
    }
    request = Request(url, headers=headers)

    for attempt in range(3):
        try:
            with urlopen(request, timeout=10) as response:
                content = response.read().decode("utf-8", errors="ignore")
            break
        except urllib.error.HTTPError as e:
            if e.code == 404: # Not found (Holiday/Weekend)
                _BHAVCOPY_CACHE[key] = None
                with open(missing_path, 'w') as f: f.write("") # Remember it's missing permanently
                return None
            time.sleep(2.0 + attempt)
        except Exception:
            time.sleep(2.0 + attempt)
    else:
        # Failed after retries
        print(f"Warning: Failed to fetch {key} due to rate limits.")
        return None
        
    try:
        df = pd.read_csv(StringIO(content), engine="python", on_bad_lines="skip")
        df.columns = [str(c).strip().upper() for c in df.columns]
        
        # PRE-PROCESS ONCE: Extract required columns and set index for O(1) lookups
        symbol_col = _find_column(df.columns.tolist(), ["SYMBOL"])
        series_col = _find_column(df.columns.tolist(), ["SERIES"])
        open_col = _find_column(df.columns.tolist(), ["OPEN_PRICE", "OPEN"])
        high_col = _find_column(df.columns.tolist(), ["HIGH_PRICE", "HIGH"])
        low_col = _find_column(df.columns.tolist(), ["LOW_PRICE", "LOW"])
        close_col = _find_column(df.columns.tolist(), ["CLOSE_PRICE", "CLOSE", "CLOSE_PRICE_"])
        volume_col = _find_column(df.columns.tolist(), ["TOTTRDQTY", "TTL_TRD_QNTY", "VOLUME", "TOTTRD_QTY"])
        
        if not (symbol_col and series_col and open_col and high_col and low_col and close_col):
            _BHAVCOPY_CACHE[key] = None
            return None
            
        df[symbol_col] = df[symbol_col].astype(str).str.strip().str.upper()
        df[series_col] = df[series_col].astype(str).str.strip().str.upper()
        
        # Filter EQ only
        df = df[df[series_col] == "EQ"]
        
        # Rename and keep only necessary columns
        rename_dict = {
            open_col: "OPEN", high_col: "HIGH", low_col: "LOW", close_col: "CLOSE"
        }
        if volume_col:
            rename_dict[volume_col] = "VOLUME"
            
        df = df.rename(columns=rename_dict)
        if "VOLUME" not in df.columns:
            df["VOLUME"] = 0.0
            
        # Set symbol as index for instant lookups
        df = df.set_index(symbol_col)[["OPEN", "HIGH", "LOW", "CLOSE", "VOLUME"]]
        df = df.apply(pd.to_numeric, errors="coerce")
        
        # Save to disk cache for future runs
        df.to_parquet(disk_path)
        
        _BHAVCOPY_CACHE[key] = df
        return df
    except Exception:
        # Parse error
        _BHAVCOPY_CACHE[key] = None
        return None

def _find_column(columns: Any, candidates: Sequence[str]) -> Optional[str]:
    lookup = {str(c).strip().upper(): c for c in columns}
    for candidate in candidates:
        if candidate in lookup:
            return lookup[candidate]
    return None

def fetch_daily_candles(symbol: str, as_of_date: date, lookback_days: int = 320) -> Optional[pd.DataFrame]:
    """Fetch a history of daily candles for a given symbol up to as_of_date."""
    rows: List[Dict[str, Any]] = []

    # 1. Pre-fetch all missing days in parallel to drastically speed up network I/O
    days_to_fetch = [as_of_date - timedelta(days=offset) for offset in range(lookback_days + 1)]
    missing_days = []
    for d in days_to_fetch:
        key = d.strftime("%Y-%m-%d")
        if key not in _BHAVCOPY_CACHE and not os.path.exists(os.path.join(_CACHE_DIR, f"{key}.parquet")) and not os.path.exists(os.path.join(_CACHE_DIR, f"{key}.missing")):
            missing_days.append(d)
    
    if missing_days:
        # Reduced max_workers to 3 to respect NSE rate limits during large historical lookbacks
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(_download_bhavcopy_for_date, missing_days))

    # 2. Extract data sequentially (all requests will now instantly hit the RAM cache)
    for day in days_to_fetch:
        df = _download_bhavcopy_for_date(day)
        if df is None or df.empty:
            continue

        if symbol in df.index:
            r = df.loc[symbol]
            # Some Bhavcopies have duplicate EQ entries accidentally, take the first one
            if isinstance(r, pd.DataFrame):
                r = r.iloc[0]
                
            if pd.isna(r["OPEN"]) or pd.isna(r["CLOSE"]):
                continue
                
            rows.append({
                "Date": pd.to_datetime(day),
                "Open": float(r["OPEN"]),
                "High": float(r["HIGH"]),
                "Low": float(r["LOW"]),
                "Close": float(r["CLOSE"]),
                "Volume": float(r["VOLUME"]) if not pd.isna(r["VOLUME"]) else 0.0
            })

    if not rows:
        return None

    daily = (
        pd.DataFrame(rows)
        .dropna(subset=["Date", "Open", "High", "Low", "Close"])
        .sort_values("Date")
        .drop_duplicates(subset=["Date"], keep="last")
        .set_index("Date")
    )

    if len(daily) < 10:  # Minimum valid days to form a DataFrame
        return None

    return daily

def fetch_bulk_history(symbols: List[str], end_date: date, lookback_days: int) -> Dict[str, pd.DataFrame]:
    """Highly optimized vectorized fetcher that returns history for multiple symbols in one pass."""
    days_to_fetch = [end_date - timedelta(days=offset) for offset in range(lookback_days + 1)]
    missing_days = []
    for d in days_to_fetch:
        key = d.strftime("%Y-%m-%d")
        if key not in _BHAVCOPY_CACHE and not os.path.exists(os.path.join(_CACHE_DIR, f"{key}.parquet")) and not os.path.exists(os.path.join(_CACHE_DIR, f"{key}.missing")):
            missing_days.append(d)
    
    if missing_days:
        # Reduced max_workers to 3 to respect NSE rate limits during large historical lookbacks
        with ThreadPoolExecutor(max_workers=3) as executor:
            list(executor.map(_download_bhavcopy_for_date, missing_days))
            
    all_dfs = []
    for day in days_to_fetch:
        df = _download_bhavcopy_for_date(day)
        if df is not None and not df.empty:
            df = df.copy()
            df['Date'] = pd.to_datetime(day)
            all_dfs.append(df)
            
    if not all_dfs:
        return {}
        
    master_df = pd.concat(all_dfs).reset_index()
    master_df = master_df[master_df['SYMBOL'].isin(symbols)]
    master_df = master_df.rename(columns={"OPEN": "Open", "HIGH": "High", "LOW": "Low", "CLOSE": "Close", "VOLUME": "Volume"})
    master_df = master_df.dropna(subset=["Date", "Open", "High", "Low", "Close"])
    master_df = master_df.sort_values(by=["SYMBOL", "Date"])
    master_df = master_df.drop_duplicates(subset=["SYMBOL", "Date"], keep="last")
    
    history = {}
    for symbol, group in master_df.groupby("SYMBOL"):
        daily = group.set_index("Date")[["Open", "High", "Low", "Close", "Volume"]]
        if len(daily) >= 10:
            
            # --- Exact Corporate Action Adjustments ---
            # Create a separate Raw_Close column before any adjustment
            daily['Raw_Close'] = daily['Close']
            
            # Load real corporate actions
            actions_lookup = {}
            try:
                actions_file = os.path.join(os.path.dirname(__file__), "corporate_actions.json")
                if os.path.exists(actions_file):
                    with open(actions_file, "r") as f:
                        all_actions = json.load(f)
                        actions_lookup = all_actions.get(symbol, {})
            except Exception as e:
                # logger.warning(f"Failed to load corporate actions for {symbol}: {e}")
                pass
                
            for d_str, factor in actions_lookup.items():
                ex_date = pd.to_datetime(d_str)
                # Apply backward multiplicative adjustment
                mask = daily.index < ex_date
                if mask.any():
                    for col in ['Open', 'High', 'Low', 'Close']:
                        daily.loc[mask, col] = daily.loc[mask, col] / factor
                    daily.loc[mask, 'Volume'] = daily.loc[mask, 'Volume'] * factor
                    # logger.info(f"Auto-Adjusted {symbol} on {d_str} for exact 1:{factor} split via lookup")

            # --- Corporate Action Sanity Check ---
            # Calculate daily returns to find unverified gaps after adjustments
            daily['Return'] = daily['Close'].pct_change()
            
            # Find significant jumps (>20% absolute)
            anomalies = daily[daily['Return'].abs() > 0.20]
            
            if not anomalies.empty:
                for date_idx, row in anomalies.iterrows():
                    d_str = date_idx.strftime("%Y-%m-%d")
                    # If this date wasn't already handled as a split
                    if d_str not in actions_lookup:
                        ret = row['Return']
                        # logger.warning(f"Unverified Data Anomaly: {symbol} on {d_str} jumped {ret*100:.1f}%. Not auto-adjusting.")
                    
            # Drop the temp column to keep df clean
            daily = daily.drop(columns=['Return'])
            
            history[symbol] = daily
            
    return history

# --- Symbol Loaders ---

def _load_symbols_from_csv_urls(
    urls: Sequence[str],
    column_name: str = "SYMBOL",
    request_timeout: int = 20,
) -> List[str]:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "text/csv,text/plain,*/*",
    }
    last_error: Optional[Exception] = None
    for url in urls:
        try:
            request = Request(url, headers=headers)
            with urlopen(request, timeout=request_timeout) as response:
                content = response.read().decode("utf-8", errors="ignore")

            raw = pd.read_csv(
                StringIO(content),
                skipinitialspace=True,
                engine="python",
                on_bad_lines="skip",
            )
            raw.columns = [str(c).strip().upper() for c in raw.columns]

            col = column_name.strip().upper()
            if col not in raw.columns:
                raise RuntimeError(f"Unable to find {col} column in CSV: {url}")

            symbols = raw[col].astype(str).str.strip().str.upper()
            symbols = symbols[symbols.str.match(r"^[A-Z0-9&\-]+$")]
            symbols = symbols[symbols != col]

            unique_sorted = sorted(set(symbols.tolist()))
            if unique_sorted:
                return unique_sorted
        except Exception as exc:
            last_error = exc
            continue

    raise RuntimeError(f"Unable to load symbols from all sources. Last error: {last_error}")

def load_nifty500_symbols() -> List[str]:
    """Fetch NIFTY 500 constituent symbols."""
    urls = [
        "https://niftyindices.com/IndexConstituent/ind_nifty500list.csv",
        "https://www.niftyindices.com/IndexConstituent/ind_nifty500list.csv",
    ]
    return _load_symbols_from_csv_urls(urls, column_name="Symbol")

def get_ohlcv(symbol: str, start: date, end: date) -> Optional[pd.DataFrame]:
    """
    Wrapper for screening engine. Fetches OHLCV, handles circuits and corporate action gaps.
    Returns DataFrame indexed by date with columns [Open, High, Low, Close, Volume, is_circuit_day].
    """
    lookback = (end - start).days
    if lookback < 0:
        return None
        
    df = fetch_daily_candles(symbol, end, lookback_days=lookback)
    if df is None or df.empty:
        return None
        
    # Trim to exact start date (since lookback includes weekends/holidays)
    df = df[df.index >= pd.to_datetime(start)]
    
    if df.empty:
        return None
        
    # 2. Handle NSE-specific issues
    # Flag circuit days: High == Low (no trading range, usually stuck at upper/lower circuit)
    df["is_circuit_day"] = df["High"] == df["Low"]
    
    # Flag corporate actions (large overnight gaps > 20% indicative of splits/bonuses)
    prev_close = df["Close"].shift(1)
    gap_pct = abs((df["Open"] - prev_close) / prev_close)
    df["is_corporate_action_gap"] = gap_pct > 0.20
    
    return df

