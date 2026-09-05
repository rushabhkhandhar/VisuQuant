"""
VisuQuant Pro Terminal - Algorithmic Trend Screener (E19 Confluence Engine)
Scans NIFTY 500 for Dual Anchored VWAP alignment, Volatility Contraction (VCP),
institutional liquidity momentum, and dynamic market regime states.
Zero third-party scraping dependencies. TVDatafeed & Local Parquet Cache native.
"""

import os
import logging
from datetime import date, datetime, timedelta
from typing import Any, Callable, Dict, List, Optional
import numpy as np
import pandas as pd
import talib

from src.data.live_tv_fetcher import get_tv_fetcher
from src.data.nse_fetcher import load_nifty500_symbols, load_nifty500_industry_mapping

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


def resolve_effective_market_date(as_of_date: Optional[Any] = None) -> date:
    """
    Normalizes user-supplied date or current time to the most recent completed market trading session.
    Rolls weekends (Saturday/Sunday) and pre-market morning hours back to Friday EOD.
    """
    if as_of_date is not None:
        if isinstance(as_of_date, str):
            try:
                target = datetime.strptime(as_of_date.strip(), "%Y-%m-%d").date()
            except Exception:
                target = date.today()
        elif isinstance(as_of_date, datetime):
            target = as_of_date.date()
        elif isinstance(as_of_date, date):
            target = as_of_date
        else:
            target = date.today()
    else:
        now_dt = datetime.now()
        cur_date = now_dt.date()
        weekday = cur_date.weekday()

        if weekday == 5:  # Saturday -> Friday
            return cur_date - timedelta(days=1)
        elif weekday == 6:  # Sunday -> Friday
            return cur_date - timedelta(days=2)
        elif now_dt.hour < 9 or (now_dt.hour == 9 and now_dt.minute < 15):
            return cur_date - timedelta(days=3 if weekday == 0 else 1)
        else:
            return cur_date

    # For user-specified date, ensure it does not land on a weekend
    weekday = target.weekday()
    if weekday == 5:  # Saturday
        return target - timedelta(days=1)
    elif weekday == 6:  # Sunday
        return target - timedelta(days=2)
    return target


def compute_market_breadth(bulk_data: Dict[str, pd.DataFrame], as_of: pd.Timestamp) -> float:
    """Calculates fraction of stocks trading strictly above their 50-day SMA."""
    above = 0
    valid = 0
    for df in bulk_data.values():
        history = df[df.index <= as_of]
        if len(history) < 50:
            continue
        sma50 = history["Close"].rolling(50).mean().iloc[-1]
        close = history["Close"].iloc[-1]
        if pd.notna(sma50) and pd.notna(close):
            valid += 1
            if close > sma50:
                above += 1
    return (above / valid) if valid > 0 else 0.5


def compute_market_bcr(bulk_data: Dict[str, pd.DataFrame], as_of: pd.Timestamp) -> float:
    """Calculates Breakout Continuation Rate (BCR) across the universe."""
    lookback_days = 120
    embargo_days = 30
    outcome_sessions = 20

    start = as_of - pd.Timedelta(days=lookback_days)
    end = as_of - pd.Timedelta(days=embargo_days)
    outcomes = []

    for df in bulk_data.values():
        if len(df) < 60:
            continue
        history = df[df.index <= as_of]
        highs = history["High"].rolling(40).max().shift(1)
        window = history[(history.index >= start) & (history.index <= end)]
        for timestamp in window.index:
            try:
                pos = history.index.get_loc(timestamp)
                if pos + outcome_sessions >= len(history):
                    continue
                if pd.notna(highs.iloc[pos]) and history["Close"].iloc[pos] > highs.iloc[pos]:
                    outcomes.append(
                        1 if history["Close"].iloc[pos + outcome_sessions] > history["Close"].iloc[pos] else 0
                    )
            except Exception:
                continue

    return (sum(outcomes) / len(outcomes)) if len(outcomes) >= 10 else 0.50


def run_e19_screener(
    as_of_date: Optional[Any] = None,
    top_n: int = 10,
    check_regime: bool = True,
    progress_callback: Optional[Callable[[str, str], None]] = None,
) -> Dict[str, Any]:
    """
    Executes the canonical E19 Confluence Engine scan:
    - Dual Anchored VWAP Confluence (200d Major Swing Low + 60d Tactical Swing Low)
    - Volatility Contraction Pattern (VCP) Breakouts
    - Dynamic 20/50 EMA Trend Pullback Bounces
    - Multi-factor Market Regime Filter (Breadth + BCR)
    - 2:1 Reward-to-Risk Enforcement (2.0x ATR Stop Loss, 4.0x ATR Target)
    """
    def log(msg: str, level: str = "INFO"):
        if progress_callback:
            progress_callback(msg, level)
        if level == "WARNING":
            logger.warning(msg)
        elif level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)

    effective_date = resolve_effective_market_date(as_of_date)
    log(f"--- Starting E19 Confluence Screener for {effective_date.strftime('%Y-%m-%d')} ---")

    # 1. Load Universe
    universe = load_nifty500_symbols()
    if "NIFTYBEES" not in universe:
        universe.append("NIFTYBEES")
    log(f"Loaded NIFTY 500 universe ({len(universe)} symbols).")

    # 2. Fetch/Load Cached Data via TVDatafeed & Local Parquet
    log("Synchronizing multi-timeframe price history via TVDatafeed & Parquet cache...")
    fetcher = get_tv_fetcher()
    bulk_data = fetcher.fetch_bulk_live_cached(universe, n_bars=250)
    log(f"Market database ready with {len(bulk_data)} active securities.")

    if not bulk_data:
        log("No market data available for evaluation.", level="ERROR")
        return {"status": "error", "message": "Failed to load market candles."}

    # 3. Multi-Factor Market Regime Analysis
    as_of_ts = pd.Timestamp(effective_date)
    breadth = compute_market_breadth(bulk_data, as_of_ts)
    bcr = compute_market_bcr(bulk_data, as_of_ts)

    # Benchmark trend
    nifty_df = bulk_data.get("NIFTYBEES")
    if nifty_df is None or nifty_df.empty:
        nifty_df = fetcher.fetch_symbol("NIFTY", n_bars=250)

    nifty_close = 0.0
    nifty_sma200 = 0.0
    if nifty_df is not None and not nifty_df.empty and len(nifty_df) >= 50:
        nifty_close = float(nifty_df["Close"].iloc[-1])
        nifty_sma200 = float(nifty_df["Close"].rolling(min(200, len(nifty_df))).mean().iloc[-1])

    macro_bullish = nifty_close >= nifty_sma200 if nifty_sma200 > 0 else True

    # E19 Multi-Factor Regime State
    if breadth >= 0.40 and bcr >= 0.50 and macro_bullish:
        regime_label = "BULLISH TREND (Breakout Expansion)"
        regime_state = 1
    elif breadth >= 0.25:
        regime_label = "CHOPPY / PULLBACK (Tactical Mean-Reversion)"
        regime_state = 2
    else:
        regime_label = "DEFENSIVE / RISK-OFF (Cash Preservation)"
        regime_state = 3

    log("=========================================")
    log(f"MARKET REGIME: {regime_label}")
    log(f"Market Breadth (>50 SMA): {breadth * 100:.1f}% | Breakout Continuation Rate (BCR): {bcr * 100:.1f}%")
    log("=========================================")

    # 4. Candidate Screening & Confluence Evaluation
    log("Scanning NIFTY 500 for Dual AVWAP, VCP Contraction, and Dynamic Pullback setups...")
    industry_map = load_nifty500_industry_mapping()
    candidates: List[Dict[str, Any]] = []

    excluded_sectors = ["Construction Materials", "Oil Gas & Consumable Fuels", "Power"]

    for sym, df in bulk_data.items():
        if sym in ["NIFTYBEES", "NIFTY", "BANKNIFTY"]:
            continue
        if len(df) < 120:
            continue

        history = df[df.index <= as_of_ts]
        if len(history) < 120:
            continue

        close = float(history["Close"].iloc[-1])
        if close < 40.0:  # Avoid illiquid micro-caps
            continue

        sector = industry_map.get(sym, "Nifty 500")

        # Technical Baselines
        sma200 = float(history["Close"].rolling(min(200, len(history)), min_periods=40).mean().iloc[-1])
        ema50 = float(history["Close"].ewm(span=50, adjust=False).mean().iloc[-1])
        ema20 = float(history["Close"].ewm(span=20, adjust=False).mean().iloc[-1])

        # Core Macro Filter: Price above long-term baseline (or 50 EMA above 200 SMA)
        if close < sma200 or ema50 < sma200:
            continue

        # ATR 14
        atr = talib.ATR(history["High"], history["Low"], history["Close"], timeperiod=14).iloc[-1]
        if pd.isna(atr) or atr <= 0:
            continue
        atr = float(atr)

        cur_vol = float(history["Volume"].iloc[-1])
        vol_sma20 = float(history["Volume"].rolling(20, min_periods=5).mean().iloc[-1])

        high_52w = float(history["High"].rolling(min(250, len(history)), min_periods=40).max().iloc[-1])
        dist_52w = (close - high_52w) / high_52w if high_52w > 0 else -1.0

        # --- SETUP 1: Dual AVWAP Confluence ---
        # 1. 200-day major swing low AVWAP
        lookback_200 = min(len(history), 200)
        major_df = history.iloc[-lookback_200:]
        min_pos_200 = int(np.argmin(major_df["Low"].values))
        major_slice = major_df.iloc[min_pos_200:]
        avwap_200 = 0.0
        if len(major_slice) >= 5:
            tp_200 = (major_slice["High"] + major_slice["Low"] + major_slice["Close"]) / 3.0
            v_200 = major_slice["Volume"]
            avwap_200 = float(((tp_200 * v_200).cumsum() / (v_200.cumsum() + 1e-5)).iloc[-1])

        # 2. 60-day tactical swing low AVWAP
        lookback_60 = min(len(history), 60)
        recent_df = history.iloc[-lookback_60:]
        min_pos_60 = int(np.argmin(recent_df["Low"].values))
        tactical_slice = recent_df.iloc[min_pos_60:]
        avwap_60 = 0.0
        if len(tactical_slice) >= 3:
            tp_60 = (tactical_slice["High"] + tactical_slice["Low"] + tactical_slice["Close"]) / 3.0
            v_60 = tactical_slice["Volume"]
            avwap_60 = float(((tp_60 * v_60).cumsum() / (v_60.cumsum() + 1e-5)).iloc[-1])

        is_dual_avwap = (
            avwap_200 > 0
            and close >= avwap_200
            and avwap_60 > 0
            and abs(close - avwap_60) / avwap_60 <= 0.04
        )

        # --- SETUP 2: Dynamic Pullback Bounce ---
        dist_ema20 = (close - ema20) / ema20
        dist_ema50 = (close - ema50) / ema50
        is_pullback = (
            (-0.03 <= dist_ema20 <= 0.035 or -0.025 <= dist_ema50 <= 0.025)
            and float(history["Low"].iloc[-1]) <= ema20 * 1.02
        )

        # --- SETUP 3: Volatility Contraction Pattern (VCP) ---
        is_vcp = False
        if len(history) >= 20:
            range_10d = (history["High"].iloc[-10:].max() - history["Low"].iloc[-10:].min()) / close
            range_20d = (history["High"].iloc[-20:].max() - history["Low"].iloc[-20:].min()) / close
            if range_10d < 0.10 and range_10d < range_20d and dist_52w >= -0.20:
                is_vcp = True

        # --- SETUP 4: Institutional Momentum Breakout ---
        is_momentum = (dist_52w >= -0.12) and (close >= ema20)

        if not (is_dual_avwap or is_pullback or is_vcp or is_momentum):
            continue

        # Alpha Scoring
        score = 0.0
        triggers = []
        if is_dual_avwap:
            score += 35.0
            triggers.append("Dual AVWAP")
        if is_pullback:
            score += 30.0
            triggers.append("EMA Pullback")
        if is_vcp:
            score += 25.0
            triggers.append("VCP Compression")
        if is_momentum:
            score += 20.0
            if dist_52w >= -0.05:
                score += 10.0
        if vol_sma20 > 0 and cur_vol >= vol_sma20:
            score += 15.0

        trigger_name = "E19 " + " + ".join(triggers[:2]) if triggers else "E19 Confluence"

        # 2:1 Reward to Risk: 2x ATR SL, 4x ATR Target
        sl = round(close - (2.0 * atr), 2)
        target = round(close + (4.0 * atr), 2)

        candidates.append({
            "symbol": sym,
            "close": round(close, 2),
            "entry_price": round(close, 2),
            "stop_loss": sl,
            "target": target,
            "risk_reward": 2.0,
            "score": round(score, 1),
            "alpha_score": round(score, 1),
            "trigger_type": trigger_name,
            "strategy_name": trigger_name,
            "industry": sector,
            "sector": sector,
        })

    # Sort candidates by institutional alpha score descending
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:top_n] if top_n else candidates

    log(f"Screener complete: Identified {len(candidates)} qualified setups across NIFTY 500.")
    log(f"Selecting top {len(top_candidates)} institutional candidates:")
    for rank, c in enumerate(top_candidates, 1):
        log(f"#{rank} {c['symbol']} (CMP: ₹{c['close']}) | SL: ₹{c['stop_loss']} | Target: ₹{c['target']} | {c['trigger_type']}")

    return {
        "status": "success",
        "regime": regime_label,
        "regime_state": regime_state,
        "bcr": round(float(bcr), 4),
        "breadth": round(float(breadth), 4),
        "as_of_date": str(effective_date),
        "total_scanned": len(bulk_data),
        "total_qualified": len(candidates),
        "candidates": top_candidates,
    }
