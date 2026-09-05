"""
VisuQuant Pro Terminal - Interactive Chart Service
Handles ticker resolution, historical data retrieval, and technical indicator computations
(AVWAP, 20/50/200 EMA, Bollinger Bands, Wilder's RSI, and MACD).
"""

from datetime import date as dt_date
from typing import Any, Dict
import numpy as np
import pandas as pd
import yfinance as yf


def resolve_symbol_to_ticker(raw_symbol: str) -> tuple[str, str]:
    """
    Normalizes user-supplied symbol into an institutional ticker and display name.
    """
    sym = raw_symbol.strip().upper()
    clean = (
        sym.replace("NSE:", "")
        .replace("BSE:", "")
        .replace(".NS", "")
        .replace(".BO", "")
        .strip()
    )

    if clean in ["NIFTY", "NIFTY 50", "^NSEI", "NIFTY50"]:
        return "^NSEI", "NIFTY 50"
    elif clean in ["BANKNIFTY", "BANK NIFTY", "^NSEBANK"]:
        return "^NSEBANK", "BANK NIFTY"
    elif clean in ["SENSEX", "^BSESN"]:
        return "^BSESN", "SENSEX"
    else:
        return f"{clean}.NS", clean


def compute_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates technical indicators for chart overlay and oscillators:
    - 20, 50, 200 EMAs
    - Bollinger Bands (20, 2)
    - 14-period Wilder's RSI
    - MACD (12, 26, 9)
    - Cumulative Anchored VWAP
    """
    df = df.copy()

    # Exponential Moving Averages
    df["EMA20"] = df["Close"].ewm(span=20, adjust=False).mean()
    df["EMA50"] = df["Close"].ewm(span=50, adjust=False).mean()
    df["EMA200"] = df["Close"].ewm(span=200, adjust=False).mean()

    # Bollinger Bands (20, 2)
    sma20 = df["Close"].rolling(window=20, min_periods=1).mean()
    std20 = df["Close"].rolling(window=20, min_periods=1).std().fillna(0)
    df["BB_Upper"] = sma20 + (std20 * 2)
    df["BB_Lower"] = sma20 - (std20 * 2)

    # Wilder's 14-period RSI
    delta = df["Close"].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=13, adjust=False).mean()
    avg_loss = loss.ewm(com=13, adjust=False).mean()
    rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0)
    df["RSI"] = np.where(np.isnan(rs), 50.0, 100 - (100 / (1 + rs)))

    # MACD (12, 26, 9)
    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()
    df["MACD"] = macd
    df["MACD_Signal"] = macd_signal
    df["MACD_Hist"] = macd - macd_signal

    # Anchored VWAP (cumulative across loaded time series)
    vol = df["Volume"].values
    typical_price = ((df["High"] + df["Low"] + df["Close"]) / 3.0).values
    cum_vol = np.cumsum(vol)
    cum_vp = np.cumsum(typical_price * vol)
    df["AVWAP"] = np.where(cum_vol > 0, cum_vp / cum_vol, df["Close"].values)

    return df


def fetch_chart_payload(symbol: str, period: str = "6mo") -> Dict[str, Any]:
    """
    Fetches market candle history and formats indicator series for Lightweight Charts.
    """
    try:
        raw_sym = symbol.strip().upper()
        ticker_str, display_sym = resolve_symbol_to_ticker(raw_sym)

        # Primary attempt: Yahoo Finance
        t = yf.Ticker(ticker_str)
        df = t.history(period=period)

        # Fallback to BSE suffix if NSE returned empty
        if df.empty and not ticker_str.endswith(".BO") and not ticker_str.startswith("^"):
            bse_ticker = f"{display_sym}.BO"
            df = yf.Ticker(bse_ticker).history(period=period)

        # Fallback to local Bhavcopy daily history cache
        if df.empty:
            from src.data.nse_fetcher import fetch_bulk_history
            lookback = 30 if period == "1mo" else 90 if period == "3mo" else 365 if period == "1y" else 180
            bulk = fetch_bulk_history([display_sym], dt_date.today(), lookback)
            if display_sym in bulk and not bulk[display_sym].empty:
                df = bulk[display_sym].copy()

        if df.empty:
            return {
                "status": "error",
                "message": f"Symbol '{raw_sym}' is not a valid NSE/BSE ticker or has no trading data.",
            }

        df = compute_indicators(df)

        candles = []
        volume = []
        avwap_data = []
        ema20_data = []
        ema50_data = []
        ema200_data = []
        bb_upper_data = []
        bb_lower_data = []
        rsi_data = []
        macd_data = []
        macd_signal_data = []
        macd_hist_data = []

        for idx, row in df.iterrows():
            time_str = idx.strftime("%Y-%m-%d")
            o = round(float(row["Open"]), 2)
            h = round(float(row["High"]), 2)
            l = round(float(row["Low"]), 2)
            c = round(float(row["Close"]), 2)
            vol = int(row["Volume"]) if not np.isnan(row["Volume"]) else 0

            candles.append({"time": time_str, "open": o, "high": h, "low": l, "close": c})
            volume.append({
                "time": time_str,
                "value": vol,
                "color": "rgba(0, 255, 136, 0.5)" if c >= o else "rgba(255, 51, 102, 0.5)",
            })

            avwap_data.append({"time": time_str, "value": round(float(row["AVWAP"]), 2)})
            ema20_data.append({"time": time_str, "value": round(float(row["EMA20"]), 2)})
            ema50_data.append({"time": time_str, "value": round(float(row["EMA50"]), 2)})
            ema200_data.append({"time": time_str, "value": round(float(row["EMA200"]), 2)})
            bb_upper_data.append({"time": time_str, "value": round(float(row["BB_Upper"]), 2)})
            bb_lower_data.append({"time": time_str, "value": round(float(row["BB_Lower"]), 2)})

            rsi_val = round(float(row["RSI"]), 2) if not np.isnan(row["RSI"]) else 50.0
            rsi_data.append({"time": time_str, "value": rsi_val})

            macd_data.append({"time": time_str, "value": round(float(row["MACD"]), 2)})
            macd_signal_data.append({"time": time_str, "value": round(float(row["MACD_Signal"]), 2)})
            m_hist = round(float(row["MACD_Hist"]), 2)
            macd_hist_data.append({
                "time": time_str,
                "value": m_hist,
                "color": "rgba(0, 255, 136, 0.6)" if m_hist >= 0 else "rgba(255, 51, 102, 0.6)",
            })

        return {
            "status": "success",
            "symbol": display_sym,
            "candles": candles,
            "volume": volume,
            "avwap": avwap_data,
            "ema20": ema20_data,
            "ema50": ema50_data,
            "ema200": ema200_data,
            "bb_upper": bb_upper_data,
            "bb_lower": bb_lower_data,
            "rsi": rsi_data,
            "macd": macd_data,
            "macd_signal": macd_signal_data,
            "macd_hist": macd_hist_data,
        }
    except Exception as e:
        return {"status": "error", "message": str(e)}
