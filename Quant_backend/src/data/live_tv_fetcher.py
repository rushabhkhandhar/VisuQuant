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

