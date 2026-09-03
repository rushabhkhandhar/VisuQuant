import os
import time
import logging
from typing import Dict, List, Optional
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tvDatafeed import TvDatafeed, Interval

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

class LiveTVFetcher:
    def __init__(self):
        # We initialize without login, but keep it silent unless it warns
        self.username = None
        self.password = None
        self.tv = TvDatafeed()

    def fetch_symbol(self, symbol: str, n_bars: int = 200, retries: int = 2) -> Optional[pd.DataFrame]:
        """Fetch historical daily candles (including the current live daily candle) for a single symbol."""
        for attempt in range(retries + 1):
            try:
                # We request NSE exchange by default.
                df = self.tv.get_hist(symbol=symbol, exchange='NSE', interval=Interval.in_daily, n_bars=n_bars)
                
                if df is None or df.empty:
                    if attempt < retries:
                        logger.debug(f"Empty data for {symbol}, possible dead connection. Reconnecting...")
                        try:
                            self.tv = TvDatafeed()
                        except:
                            pass
                        time.sleep(2)
                        continue
                    return None
                    
                # Format to match our strategy's expected schema: [Open, High, Low, Close, Volume]
                # tvDatafeed returns lower case columns: symbol, open, high, low, close, volume
                df = df.rename(columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume"
                })
                
                # Keep only necessary columns
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                
                # The index is already datetime
                time.sleep(0.8) # Anti rate-limit sleep (increased for stability)
                return df
                
            except Exception as e:
                if attempt < retries:
                    logger.debug(f"Retrying {symbol} daily fetch after error: {e}")
                    time.sleep(2)
                    # Force reconnect if connection was lost
                    if "Connection" in str(e) or "timeout" in str(e).lower() or "lost" in str(e).lower():
                        try:
                            self.tv = TvDatafeed()
                            time.sleep(2)
                        except:
                            pass
                else:
                    logger.debug(f"Failed to fetch {symbol} after {retries} retries: {e}")
                    return None
                    
        return None

    def fetch_bulk_live(self, symbols: List[str], n_bars: int = 200, max_workers: int = 1) -> Dict[str, pd.DataFrame]:
        """
        Fetch historical daily candles for a list of symbols sequentially.
        TradingView's WebSocket connection is not thread-safe, and opening multiple 
        concurrent WebSockets risks immediate IP-bans.
        """
        results = {}
        total = len(symbols)
        logger.info(f"Fetching live data for {total} symbols using TradingView (Sequential Mode)...")
        
        start_time = time.time()
        
        for i, sym in enumerate(symbols, 1):
            if i % 50 == 0:
                logger.info(f"Progress: {i}/{total} symbols fetched. Cooling down for 5 seconds...")
                time.sleep(5)
            elif i == total:
                logger.info(f"Progress: {i}/{total} symbols fetched...")
                
            try:
                df = self.fetch_symbol(sym, n_bars)
                if df is not None and not df.empty:
                    if len(df) >= min(10, n_bars):
                        results[sym] = df
            except Exception as e:
                logger.debug(f"Error fetching {sym}: {e}")
                
        elapsed = time.time() - start_time
        logger.info(f"Successfully fetched data for {len(results)}/{total} symbols in {elapsed:.2f} seconds.")
        
        return results

    def fetch_bulk_live_cached(self, symbols: List[str], n_bars: int = 220, cache_file: str = None) -> Dict[str, pd.DataFrame]:
        """
        Incrementally fetch daily candles using a local Parquet cache to drastically reduce
        fetch time from 15 minutes to ~30-60 seconds.
        Only fetches recent delta candles for each symbol and updates the cache.
        """
        if cache_file is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            cache_dir = os.path.join(base_dir, "screener", "pipeline", "swing", "data_cache")
            os.makedirs(cache_dir, exist_ok=True)
            cache_file = os.path.join(cache_dir, "nifty500_history.parquet")

        cached_dict = {}
        cached_all = None
        if os.path.exists(cache_file):
            try:
                cached_all = pd.read_parquet(cache_file)
            except Exception as e:
                logger.warning(f"Could not load parquet cache ({e}). Trying gz backup...")
        
        gz_file = cache_file.replace(".parquet", ".csv.gz")
        if cached_all is None and os.path.exists(gz_file):
            try:
                cached_all = pd.read_csv(gz_file)
                logger.info(f"Loaded existing market data cache from GZ backup {gz_file}.")
            except Exception as e:
                logger.warning(f"Could not load GZ backup ({e}). Starting fresh.")

        if cached_all is not None and not cached_all.empty:
            if 'Symbol' in cached_all.columns:
                for sym, group in cached_all.groupby('Symbol'):
                    df_sym = group.drop(columns=['Symbol'])
                    if not isinstance(df_sym.index, pd.DatetimeIndex):
                        if 'Date' in df_sym.columns:
                            df_sym['Date'] = pd.to_datetime(df_sym['Date'])
                            df_sym = df_sym.set_index('Date')
                    cached_dict[sym] = df_sym.sort_index()
            logger.info(f"Loaded {len(cached_dict)} symbols from existing market data cache.")

        results = {}
        total = len(symbols)
        logger.info(f"Incrementally fetching live data for {total} symbols...")
        start_time = time.time()
        
        today_date = pd.Timestamp.now().date()
        needs_save = False

        for i, sym in enumerate(symbols, 1):
            if i % 50 == 0:
                logger.info(f"Progress: {i}/{total} symbols processed. Cooling down for 2 seconds...")
                time.sleep(2)

            cached_df = cached_dict.get(sym)
            if cached_df is not None and not cached_df.empty:
                max_dt = cached_df.index.max().date()
                days_gap = (today_date - max_dt).days
                if days_gap == 0:
                    # Already up-to-date today! No network request needed.
                    results[sym] = cached_df.tail(n_bars)
                    continue
                elif days_gap <= 7:
                    # Recent cache available: Only fetch the few missing bars!
                    bars_to_fetch = max(2, days_gap + 2)
                    new_df = self.fetch_symbol(sym, n_bars=bars_to_fetch)
                    if new_df is not None and not new_df.empty:
                        combined = pd.concat([cached_df, new_df])
                        combined = combined[~combined.index.duplicated(keep='last')].sort_index().tail(n_bars)
                        results[sym] = combined
                        needs_save = True
                        continue
                    else:
                        results[sym] = cached_df.tail(n_bars)
                        continue

            # Full fetch if not cached or cache is stale
            df = self.fetch_symbol(sym, n_bars=n_bars)
            if df is not None and not df.empty:
                results[sym] = df
                needs_save = True

        elapsed = time.time() - start_time
        logger.info(f"Live data ready for {len(results)}/{total} symbols in {elapsed:.2f} seconds.")

        # Save updated cache to disk
        if needs_save and results:
            try:
                records = []
                for sym, df in results.items():
                    df_copy = df.copy()
                    if not isinstance(df_copy.index, pd.DatetimeIndex):
                        if 'Date' in df_copy.columns:
                            df_copy = df_copy.set_index('Date')
                    df_copy = df_copy.reset_index()
                    if 'index' in df_copy.columns:
                        df_copy = df_copy.rename(columns={'index': 'Date'})
                    df_copy['Symbol'] = sym
                    records.append(df_copy)
                if records:
                    full_df = pd.concat(records, ignore_index=True)
                    try:
                        full_df.to_parquet(cache_file, compression='snappy')
                        logger.info(f"Persisted updated incremental cache to {cache_file} ({len(results)} symbols).")
                    except Exception as pe:
                        logger.warning(f"Parquet save skipped ({pe}). Saving gz backup...")
                    gz_file = cache_file.replace(".parquet", ".csv.gz")
                    full_df.to_csv(gz_file, index=False, compression='gzip')
            except Exception as e:
                logger.warning(f"Failed to persist cache to {cache_file}: {e}")

        return results

    def fetch_symbol_intraday(self, symbol: str, interval=Interval.in_1_hour, n_bars: int = 200, retries: int = 2) -> Optional[pd.DataFrame]:
        """Fetch intraday candles for a single symbol at any supported interval."""
        for attempt in range(retries + 1):
            try:
                df = self.tv.get_hist(symbol=symbol, exchange='NSE', interval=interval, n_bars=n_bars)
                
                if df is None or df.empty:
                    if attempt < retries:
                        logger.debug(f"Empty intraday data for {symbol}, possible dead connection. Reconnecting...")
                        try:
                            self.tv = TvDatafeed()
                        except:
                            pass
                        time.sleep(2)
                        continue
                    return None
                    
                df = df.rename(columns={
                    "open": "Open",
                    "high": "High",
                    "low": "Low",
                    "close": "Close",
                    "volume": "Volume"
                })
                
                df = df[['Open', 'High', 'Low', 'Close', 'Volume']]
                time.sleep(0.8) # Anti rate-limit sleep
                return df
                
            except Exception as e:
                if attempt < retries:
                    logger.debug(f"Retrying {symbol} intraday fetch after error: {e}")
                    time.sleep(2)
                    # Force reconnect if connection was lost
                    if "Connection" in str(e) or "timeout" in str(e).lower() or "lost" in str(e).lower():
                        try:
                            self.tv = TvDatafeed()
                            time.sleep(2)
                        except:
                            pass
                else:
                    logger.debug(f"Failed to fetch intraday {symbol} after {retries} retries: {e}")
                    return None
                    
        return None

    def fetch_bulk_intraday(self, symbols: List[str], interval=Interval.in_1_hour, n_bars: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch intraday candles for a list of symbols sequentially using TradingView."""
        results = {}
        total = len(symbols)
        logger.info(f"Fetching intraday ({interval}) data for {total} symbols (Sequential Mode)...")
        
        start_time = time.time()
        
        for i, sym in enumerate(symbols, 1):
            if i % 50 == 0:
                if self.username and self.password:
                    logger.info(f"Intraday progress: {i}/{total} symbols fetched. Cooling down for 3 seconds...")
                    time.sleep(3)
                else:
                    logger.info(f"Intraday progress: {i}/{total} symbols fetched. Cooling down for 10 seconds...")
                    time.sleep(10)
            elif i == total:
                logger.info(f"Intraday progress: {i}/{total} symbols fetched...")
                
            try:
                df = self.fetch_symbol_intraday(sym, interval=interval, n_bars=n_bars)
                if df is not None and not df.empty:
                    if len(df) >= min(10, n_bars):
                        results[sym] = df
            except Exception as e:
                logger.debug(f"Error fetching intraday {sym}: {e}")
                
        elapsed = time.time() - start_time
        logger.info(f"Intraday fetch complete: {len(results)}/{total} symbols in {elapsed:.2f} seconds.")
        
        return results

    def fetch_bulk_futures_live(self, symbols: List[str], n_bars: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch continuous futures for a list of symbols sequentially."""
        results = {}
        total = len(symbols)
        logger.info(f"Fetching live F&O futures for {total} symbols...")
        start_time = time.time()
        for i, sym in enumerate(symbols, 1):
            if i % 50 == 0:
                time.sleep(5)
            # Append 1! for continuous futures on TradingView
            future_symbol = f"{sym}1!"
            try:
                df = self.fetch_symbol(future_symbol, n_bars)
                if df is not None and not df.empty and len(df) >= min(10, n_bars):
                    # Store it back under the base symbol name
                    results[sym] = df
            except Exception as e:
                logger.debug(f"Error fetching future {future_symbol}: {e}")
        elapsed = time.time() - start_time
        logger.info(f"F&O fetch complete: {len(results)}/{total} symbols in {elapsed:.2f} seconds.")
        return results

    def fetch_bulk_futures_intraday(self, symbols: List[str], interval=Interval.in_15_minute, n_bars: int = 200) -> Dict[str, pd.DataFrame]:
        """Fetch intraday continuous futures."""
        results = {}
        total = len(symbols)
        logger.info(f"Fetching intraday F&O futures ({interval}) for {total} symbols...")
        start_time = time.time()
        for i, sym in enumerate(symbols, 1):
            if i % 50 == 0:
                time.sleep(5)
            future_symbol = f"{sym}1!"
            try:
                df = self.fetch_symbol_intraday(future_symbol, interval=interval, n_bars=n_bars)
                if df is not None and not df.empty and len(df) >= min(10, n_bars):
                    results[sym] = df
            except Exception as e:
                logger.debug(f"Error fetching intraday future {future_symbol}: {e}")
        elapsed = time.time() - start_time
        logger.info(f"Intraday F&O fetch complete: {len(results)}/{total} symbols in {elapsed:.2f} seconds.")
        return results

# Singleton instance
_fetcher = None

def get_tv_fetcher():
    global _fetcher
    if _fetcher is None:
        _fetcher = LiveTVFetcher()
    return _fetcher

def get_live_ohlcv(symbol: str, lookback: int = 200) -> Optional[pd.DataFrame]:
    """Helper for single symbol fetch matching the nse_fetcher interface style."""
    fetcher = get_tv_fetcher()
    return fetcher.fetch_symbol(symbol, n_bars=lookback)

