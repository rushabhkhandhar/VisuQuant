import os
import time
import logging
import requests
from typing import Dict, List, Optional
import pandas as pd
from concurrent.futures import ThreadPoolExecutor, as_completed
from tvDatafeed import TvDatafeed, Interval

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def sanitize_tv_symbol(symbol: str) -> str:
    """Normalize NSE/BSE ticker to TradingView naming conventions to avoid timeouts."""
    mapping = {
        "BAJAJ-AUTO": "BAJAJ_AUTO",
        "NAM-INDIA": "NAM_INDIA",
        "M&M": "M_M",
        "M&MFIN": "M_MFIN",
        "L&TFH": "L_TFH",
        "MCDOWELL-N": "UNITDSPR",
        "NIFTY 50": "NIFTY",
        "NIFTY50": "NIFTY",
        "NSEI": "NIFTY",
        "BANK NIFTY": "BANKNIFTY",
        "NSEBANK": "BANKNIFTY",
        "BSESN": "SENSEX",
    }
    clean = (
        symbol.strip()
        .upper()
        .replace("NSE:", "")
        .replace("BSE:", "")
        .replace(".NS", "")
        .replace(".BO", "")
        .replace("^", "")
        .strip()
    )
    if clean in mapping:
        return mapping[clean]
    return clean.replace("-", "_").replace("&", "_")

class LiveTVFetcher:
    def __init__(self):
        # We initialize without login, but keep it silent unless it warns
        self.username = None
        self.password = None
        self.tv = TvDatafeed()

    def fetch_symbol(
        self,
        symbol: str,
        n_bars: int = 200,
        exchange: Optional[str] = None,
        retries: int = 2,
    ) -> Optional[pd.DataFrame]:
        """Fetch historical daily candles (including the current live daily candle) for a single symbol."""
        tv_symbol = sanitize_tv_symbol(symbol)

        # Route index and exchange appropriately
        if exchange is not None:
            exchange_candidates = [exchange]
        elif tv_symbol in ["SENSEX", "BSESN"]:
            exchange_candidates = ["BSE"]
        elif tv_symbol in ["NIFTY", "BANKNIFTY", "FINNIFTY", "MIDCPNIFTY"]:
            exchange_candidates = ["NSE"]
        else:
            # Equities: try NSE first, then BSE as fallback
            exchange_candidates = ["NSE", "BSE"]

        for cur_exchange in exchange_candidates:
            for attempt in range(retries + 1):
                try:
                    df = self.tv.get_hist(
                        symbol=tv_symbol,
                        exchange=cur_exchange,
                        interval=Interval.in_daily,
                        n_bars=n_bars,
                    )

                    if df is None or df.empty:
                        if attempt < retries:
                            logger.debug(f"Empty data for {symbol} ({tv_symbol}) on {cur_exchange}, reconnecting...")
                            try:
                                self.tv = TvDatafeed()
                            except Exception:
                                pass
                            time.sleep(0.5)
                            continue
                        break  # Try next exchange candidate

                    # Format to match our strategy's expected schema: [Open, High, Low, Close, Volume]
                    df = df.rename(
                        columns={
                            "open": "Open",
                            "high": "High",
                            "low": "Low",
                            "close": "Close",
                            "volume": "Volume",
                        }
                    )

                    # Keep only necessary columns
                    df = df[["Open", "High", "Low", "Close", "Volume"]]

                    # Ensure index is DatetimeIndex
                    if not isinstance(df.index, pd.DatetimeIndex):
                        df.index = pd.to_datetime(df.index)

                    time.sleep(0.05)  # Minimal sleep for snappy interactive queries
                    return df

                except Exception as e:
                    if attempt < retries:
                        logger.debug(f"Retrying {symbol} ({tv_symbol}) on {cur_exchange} daily fetch after error: {e}")
                        time.sleep(0.5)
                        if "Connection" in str(e) or "timeout" in str(e).lower() or "lost" in str(e).lower():
                            try:
                                self.tv = TvDatafeed()
                                time.sleep(0.5)
                            except Exception:
                                pass
                    else:
                        logger.debug(f"Failed to fetch {symbol} ({tv_symbol}) on {cur_exchange} after {retries} retries: {e}")
                        break

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
        Incrementally fetch daily candles using a local Parquet cache with official NSE
        Bhavcopy batch loading and TradingView (tvdatafeed) live intraday delta candles.
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
                    if 'Date' in df_sym.columns and 'datetime' in df_sym.columns:
                        df_sym['Date'] = df_sym['Date'].fillna(df_sym['datetime'])
                        df_sym = df_sym.drop(columns=['datetime'])
                    elif 'datetime' in df_sym.columns and 'Date' not in df_sym.columns:
                        df_sym = df_sym.rename(columns={'datetime': 'Date'})
                    if 'Date' in df_sym.columns:
                        df_sym = df_sym.dropna(subset=['Date'])
                    if not isinstance(df_sym.index, pd.DatetimeIndex):
                        if 'Date' in df_sym.columns:
                            df_sym['Date'] = pd.to_datetime(df_sym['Date'])
                            df_sym = df_sym.set_index('Date')
                    cached_dict[sym] = df_sym.sort_index()
            logger.info(f"Loaded {len(cached_dict)} symbols from existing market data cache.")

        results = {}
        total = len(symbols)
        now_dt = pd.Timestamp.now()
        cur_date = now_dt.date()
        weekday = cur_date.weekday()

        # Determine latest expected trading date (handles weekends and pre-market hours)
        if weekday == 5:  # Saturday -> Friday
            latest_trading_date = cur_date - pd.Timedelta(days=1)
        elif weekday == 6:  # Sunday -> Friday
            latest_trading_date = cur_date - pd.Timedelta(days=2)
        elif now_dt.hour < 9 or (now_dt.hour == 9 and now_dt.minute < 15):
            latest_trading_date = cur_date - pd.Timedelta(days=3 if weekday == 0 else 1)
        else:
            latest_trading_date = cur_date

        today_date = latest_trading_date

        symbols_to_update = []
        needs_save = False
        start_time = time.time()

        for sym in symbols:
            cached_df = cached_dict.get(sym)
            if cached_df is not None and not cached_df.empty:
                max_val = cached_df.index.max()
                if pd.notna(max_val) and hasattr(max_val, 'date'):
                    max_dt = max_val.date()
                    if max_dt >= latest_trading_date:
                        results[sym] = cached_df.tail(n_bars)
                        continue
            symbols_to_update.append(sym)

        logger.info(f"Symbols up-to-date ({latest_trading_date}): {len(results)}/{total}. Delta needed for {len(symbols_to_update)} symbols.")

        # 1. Fast bulk fetch for latest session candles via TradingView India Scanner (0.4s for 500 stocks)
        if symbols_to_update:
            try:
                sym_to_tv = {sym: f"NSE:{sanitize_tv_symbol(sym)}" for sym in symbols_to_update}
                tv_to_sym = {v: k for k, v in sym_to_tv.items()}

                url = "https://scanner.tradingview.com/india/scan"
                payload = {
                    "symbols": {"tickers": list(sym_to_tv.values())},
                    "columns": ["name", "open", "high", "low", "close", "volume"]
                }
                headers = {
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                }
                resp = requests.post(url, json=payload, headers=headers, timeout=10)
                if resp.status_code == 200:
                    data = resp.json().get("data", [])
                    session_date_ts = pd.Timestamp(latest_trading_date)
                    still_needed = []
                    found_syms = set()

                    for item in data:
                        tv_ticker = item.get("s", "")
                        sym = tv_to_sym.get(tv_ticker)
                        d = item.get("d", [])
                        if sym and len(d) >= 6 and d[1] is not None and d[4] is not None:
                            candle_df = pd.DataFrame([{
                                'Open': float(d[1]),
                                'High': float(d[2]),
                                'Low': float(d[3]),
                                'Close': float(d[4]),
                                'Volume': float(d[5] or 0.0),
                            }], index=[session_date_ts])

                            cached_df = cached_dict.get(sym)
                            if cached_df is not None and not cached_df.empty:
                                combined = pd.concat([cached_df, candle_df])
                                combined = combined[~combined.index.duplicated(keep='last')].sort_index()
                                results[sym] = combined.tail(n_bars)
                                found_syms.add(sym)
                                needs_save = True
                            else:
                                # Full historical backfill required via tvdatafeed
                                still_needed.append(sym)

                    # Any symbol not returned by scanner or needing historical depth
                    for sym in symbols_to_update:
                        if sym not in found_syms and sym not in still_needed:
                            still_needed.append(sym)

                    logger.info(f"Updated {len(found_syms)}/{len(symbols_to_update)} symbols directly from TradingView Scanner in bulk (0.4s)! {len(still_needed)} remaining for deep historical fetch.")
                    symbols_to_update = still_needed
            except Exception as e:
                logger.warning(f"TradingView Scanner bulk fetch skipped ({e}). Falling back to individual TV datafeed.")

        # 2. Deep historical or missing market candles via TradingView (tvdatafeed)
        if symbols_to_update:
            logger.info(f"Fetching live market candles for {len(symbols_to_update)} symbols using TradingView (tvdatafeed)...")
            for i, sym in enumerate(symbols_to_update, 1):
                if i % 50 == 0:
                    logger.info(f"TradingView progress: {i}/{len(symbols_to_update)} symbols processed...")

                cached_df = cached_dict.get(sym)
                bars_to_fetch = n_bars
                if cached_df is not None and not cached_df.empty and len(cached_df) >= n_bars:
                    max_val = cached_df.index.max()
                    if pd.notna(max_val) and hasattr(max_val, 'date'):
                        days_gap = (today_date - max_val.date()).days
                        if days_gap <= 7:
                            bars_to_fetch = max(2, days_gap + 2)
                
                new_df = self.fetch_symbol(sym, n_bars=bars_to_fetch)
                if new_df is not None and not new_df.empty:
                    if cached_df is not None and not cached_df.empty:
                        combined = pd.concat([cached_df, new_df])
                        combined = combined[~combined.index.duplicated(keep='last')].sort_index()
                        results[sym] = combined.tail(n_bars)
                    else:
                        results[sym] = new_df.tail(n_bars)
                    needs_save = True
                elif cached_df is not None and not cached_df.empty:
                    results[sym] = cached_df.tail(n_bars)

        elapsed = time.time() - start_time
        logger.info(f"Live data ready for {len(results)}/{total} symbols in {elapsed:.2f} seconds.")

        # 3. Persist updated cache to disk
        if needs_save and results:
            try:
                all_to_save = dict(cached_dict)
                all_to_save.update(results)
                
                records = []
                for sym, df in all_to_save.items():
                    df_copy = df.copy()
                    if not isinstance(df_copy.index, pd.DatetimeIndex):
                        if 'Date' in df_copy.columns:
                            df_copy = df_copy.set_index('Date')
                    df_copy = df_copy.reset_index()
                    if 'index' in df_copy.columns:
                        df_copy = df_copy.rename(columns={'index': 'Date'})
                    elif 'datetime' in df_copy.columns:
                        if 'Date' in df_copy.columns:
                            df_copy['Date'] = df_copy['Date'].fillna(df_copy['datetime'])
                            df_copy = df_copy.drop(columns=['datetime'])
                        else:
                            df_copy = df_copy.rename(columns={'datetime': 'Date'})
                    if 'Date' in df_copy.columns:
                        df_copy = df_copy.dropna(subset=['Date'])
                    df_copy['Symbol'] = sym
                    records.append(df_copy)
                if records:
                    full_df = pd.concat(records, ignore_index=True)
                    try:
                        full_df.to_parquet(cache_file, compression='snappy')
                        logger.info(f"Persisted updated incremental cache to {cache_file} ({len(all_to_save)} symbols).")
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

def get_live_ohlcv(symbol: str, lookback: int = 200, exchange: Optional[str] = None) -> Optional[pd.DataFrame]:
    """Helper for single symbol fetch matching the nse_fetcher interface style."""
    fetcher = get_tv_fetcher()
    return fetcher.fetch_symbol(symbol, n_bars=lookback, exchange=exchange)

