import os
import json
import time
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime
import requests

logger = logging.getLogger(__name__)

_MARKET_CACHE: Optional[Dict[str, Any]] = None
_CACHE_TIMESTAMP: float = 0.0
_CACHE_TTL_SECONDS: float = 15.0

def _load_metadata():
    """Load local NIFTY 500 symbols and sector industry mappings."""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    data_dir = os.path.join(base_dir, "data")
    
    symbols_file = os.path.join(data_dir, "nifty500_symbols.json")
    mapping_file = os.path.join(data_dir, "nifty500_industry_mapping.json")
    
    symbols = []
    mapping = {}
    
    if os.path.exists(symbols_file):
        try:
            with open(symbols_file, "r") as f:
                symbols = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {symbols_file}: {e}")
            
    if os.path.exists(mapping_file):
        try:
            with open(mapping_file, "r") as f:
                mapping = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to read {mapping_file}: {e}")
            
    return symbols, mapping

def fetch_market_overview(force_refresh: bool = False) -> Dict[str, Any]:
    """
    Query real-time OHLCV, % change, volume, and market cap for all 500 NIFTY stocks
    via TradingView India Scanner, aggregate by sector, and calculate market movers.
    """
    global _MARKET_CACHE, _CACHE_TIMESTAMP
    
    now = time.time()
    if not force_refresh and _MARKET_CACHE is not None and (now - _CACHE_TIMESTAMP) < _CACHE_TTL_SECONDS:
        return _MARKET_CACHE

    symbols, mapping = _load_metadata()
    if not symbols:
        logger.error("No symbols available in nifty500_symbols.json")
        return _MARKET_CACHE or {"status": "error", "message": "Symbol metadata unavailable"}

    tv_tickers = [f"NSE:{s.replace('-', '_').replace('&', '_')}" for s in symbols]
    sym_map = {f"NSE:{s.replace('-', '_').replace('&', '_')}": s for s in symbols}

    url = "https://scanner.tradingview.com/india/scan"
    payload = {
        "symbols": {"tickers": tv_tickers},
        "columns": ["name", "open", "high", "low", "close", "change", "volume", "market_cap_basic"]
    }
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        t0 = time.time()
        resp = requests.post(url, json=payload, headers=headers, timeout=12)
        resp.raise_for_status()
        raw_data = resp.json().get("data", [])
        elapsed = time.time() - t0
        logger.info(f"TradingView scanner returned {len(raw_data)} symbols in {elapsed:.2f}s")
    except Exception as exc:
        logger.error(f"TradingView scanner query failed: {exc}")
        if _MARKET_CACHE is not None:
            logger.info("Serving stale cached market data as fallback.")
            return _MARKET_CACHE
        return {"status": "error", "message": f"TradingView query failed: {str(exc)}"}

    stocks = []
    sectors: Dict[str, List[Dict[str, Any]]] = {}

    for item in raw_data:
        ticker_raw = item.get("s", "")
        raw_sym = sym_map.get(ticker_raw, ticker_raw.replace("NSE:", "").replace("BSE:", ""))
        d = item.get("d", [])
        
        if len(d) >= 8 and d[4] is not None:
            change_val = round(float(d[5] or 0), 2)
            close_val = round(float(d[4] or 0), 2)
            open_val = round(float(d[1] or 0), 2)
            high_val = round(float(d[2] or 0), 2)
            low_val = round(float(d[3] or 0), 2)
            vol_val = int(d[6] or 0)
            mcap_val = float(d[7] or 0)
            
            sector_name = mapping.get(raw_sym, "Diversified")
            
            stock_info = {
                "symbol": raw_sym,
                "name": str(d[0] or raw_sym),
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close_val,
                "change": change_val,
                "volume": vol_val,
                "market_cap": mcap_val,
                "sector": sector_name
            }
            stocks.append(stock_info)
            
            if sector_name not in sectors:
                sectors[sector_name] = []
            sectors[sector_name].append(stock_info)

    if not stocks:
        return _MARKET_CACHE or {"status": "error", "message": "No valid stock records returned"}

    # Calculate Market Movers
    gainers = sorted(stocks, key=lambda x: x["change"], reverse=True)[:15]
    losers = sorted(stocks, key=lambda x: x["change"])[:15]
    most_active = sorted(stocks, key=lambda x: x["volume"], reverse=True)[:15]

    # Calculate Sector Aggregates
    sector_list = []
    total_advances = sum(1 for s in stocks if s["change"] > 0)
    total_declines = sum(1 for s in stocks if s["change"] < 0)
    total_unchanged = sum(1 for s in stocks if s["change"] == 0)

    for sec_name, sec_stocks in sectors.items():
        avg_change = round(sum(s["change"] for s in sec_stocks) / len(sec_stocks), 2)
        advances = sum(1 for s in sec_stocks if s["change"] > 0)
        declines = sum(1 for s in sec_stocks if s["change"] < 0)
        total_vol = sum(s["volume"] for s in sec_stocks)
        total_mcap = sum(s["market_cap"] for s in sec_stocks)
        
        sector_list.append({
            "sector": sec_name,
            "avg_change": avg_change,
            "count": len(sec_stocks),
            "advances": advances,
            "declines": declines,
            "total_volume": total_vol,
            "total_market_cap": total_mcap,
            # Sort stocks within sector by market cap descending
            "stocks": sorted(sec_stocks, key=lambda x: x["market_cap"], reverse=True)
        })

    # Sort sectors by highest performance first
    sector_list.sort(key=lambda x: x["avg_change"], reverse=True)

    result = {
        "status": "success",
        "timestamp": datetime.now().isoformat(),
        "total_stocks": len(stocks),
        "summary": {
            "advances": total_advances,
            "declines": total_declines,
            "unchanged": total_unchanged,
            "advance_decline_ratio": round(total_advances / max(1, total_declines), 2),
            "top_sector": sector_list[0]["sector"] if sector_list else None,
            "top_sector_change": sector_list[0]["avg_change"] if sector_list else 0.0,
            "bottom_sector": sector_list[-1]["sector"] if sector_list else None,
            "bottom_sector_change": sector_list[-1]["avg_change"] if sector_list else 0.0,
        },
        "movers": {
            "gainers": gainers,
            "losers": losers,
            "most_active": most_active,
        },
        "sectors": sector_list
    }

    _MARKET_CACHE = result
    _CACHE_TIMESTAMP = time.time()
    return result
