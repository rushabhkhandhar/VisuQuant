"""Canonical E12 near-close strategy shared by live, forward, and backtest flows."""

from __future__ import annotations

from typing import Callable, Dict, List, Optional

import pandas as pd
import talib

BCR_THRESHOLD = 0.52
BREADTH_THRESHOLD = 0.30
BCR_LOOKBACK_DAYS = 120
BCR_EMBARGO_DAYS = 30
BCR_OUTCOME_SESSIONS = 20
RISK_PRIMARY = 0.02
RISK_CONFIRMED = 0.05
RISK_ATR = 2.0
REWARD_ATR = 4.0
MAX_CONFIRMED_SIGNALS = 5
MAX_PRIMARY_SIGNALS = 5
MAX_HOLDING_SESSIONS = 5  # Quick time-based exit for Mean Reversion


def compute_bcr(bulk_data: Dict[str, pd.DataFrame], as_of_date) -> float:
    """Breakout continuation rate using only outcomes known by *as_of_date*."""
    as_of = pd.Timestamp(as_of_date)
    start = as_of - pd.Timedelta(days=BCR_LOOKBACK_DAYS)
    end = as_of - pd.Timedelta(days=BCR_EMBARGO_DAYS)
    outcomes = []
    for df in bulk_data.values():
        if len(df) < 60:
            continue
        history = df[df.index <= as_of]
        highs = history["High"].rolling(40).max().shift(1)
        window = history[(history.index >= start) & (history.index <= end)]
        for timestamp in window.index:
            position = history.index.get_loc(timestamp)
            if position + BCR_OUTCOME_SESSIONS >= len(history):
                continue
            if pd.notna(highs.iloc[position]) and history["Close"].iloc[position] > highs.iloc[position]:
                outcomes.append(
                    1 if history["Close"].iloc[position + BCR_OUTCOME_SESSIONS] > history["Close"].iloc[position] else 0
                )
    return sum(outcomes) / len(outcomes) if len(outcomes) >= 10 else 0.5


def compute_breadth(bulk_data: Dict[str, pd.DataFrame], as_of_date) -> float:
    as_of = pd.Timestamp(as_of_date)
    valid = 0
    above = 0
    for df in bulk_data.values():
        history = df[df.index <= as_of]
        if len(history) < 50:
            continue
        sma50 = history["Close"].rolling(50).mean().iloc[-1]
        if pd.notna(sma50):
            valid += 1
            above += history["Close"].iloc[-1] > sma50
    return above / valid if valid else 0.5


def build_sector_indices(bulk_data: Dict[str, pd.DataFrame], industry_mapping: Dict[str, str]) -> Dict[str, pd.DataFrame]:
    sectors: Dict[str, List[pd.Series]] = {}
    for symbol, df in bulk_data.items():
        if symbol in industry_mapping and not df.empty:
            sectors.setdefault(industry_mapping[symbol], []).append(df["Close"].pct_change().fillna(0))
    return {
        industry: pd.DataFrame({"Close": 100 * (1 + pd.concat(returns, axis=1).mean(axis=1)).cumprod()})
        for industry, returns in sectors.items()
    }


def generate_e12_signals(
    bulk_data: Dict[str, pd.DataFrame],
    nifty_hist: Optional[pd.DataFrame],
    as_of_date,
    industry_mapping: Dict[str, str],
    evaluators: Dict[str, Callable],
) -> List[dict]:
    """Return the frozen E12 MOC candidate set, ranked and capacity-limited."""
    as_of = pd.Timestamp(as_of_date)
    bcr = compute_bcr(bulk_data, as_of)
    breadth = compute_breadth(bulk_data, as_of)
    if bcr > BCR_THRESHOLD:
        state, label = 1, "Trend"
        primary, confirmation = evaluators["relative_strength"], evaluators["momentum_breakout"]
    elif breadth < BREADTH_THRESHOLD:
        return []
    else:
        state, label = 2, "MeanRev"
        primary, confirmation = evaluators["oversold_uptrend"], evaluators["trend_pullback"]

    sector_indices = build_sector_indices(bulk_data, industry_mapping)
    candidates = []
    for symbol, source_df in bulk_data.items():
        history = source_df[source_df.index <= as_of]
        if len(history) < 200:
            continue
        sector_hist = sector_indices.get(industry_mapping.get(symbol))
        if sector_hist is not None:
            sector_hist = sector_hist[sector_hist.index <= as_of]
        try:
            primary_result = primary(history, nifty_hist=nifty_hist, sector_hist=sector_hist)
            if not primary_result.get("passed", False):
                continue
            confirmation_result = confirmation(history, nifty_hist=nifty_hist, sector_hist=sector_hist)
        except Exception:
            continue

        confirmed = bool(confirmation_result and confirmation_result.get("passed", False))
        price = history["Close"].iloc[-1]
        atr = talib.ATR(history["High"], history["Low"], history["Close"], timeperiod=14).iloc[-1]
        if pd.isna(atr) or atr <= 0 or pd.isna(price) or price <= 0:
            continue
        candidates.append({
            "symbol": symbol,
            "strategy_name": f"E12-{label}-{'Confirmed' if confirmed else 'Primary'}",
            "strategy": f"E12-{label}-{'Confirmed' if confirmed else 'Primary'}",
            "action": "BUY",
            "signal_date": as_of.date().isoformat(),
            "entry_price": float(price),
            "price": float(price),
            "stop_loss": round(float(price - atr * RISK_ATR), 2),
            "target": round(float(price + atr * REWARD_ATR), 2),
            "risk_pct": RISK_CONFIRMED if confirmed else RISK_PRIMARY,
            "alpha_score": float(primary_result.get("alpha_score", 0.0)),
            "regime_state": state,
            "bcr": round(float(bcr), 4),
            "breadth": round(float(breadth), 4),
            "pending_confirmation": True,  # Fix 1: Wait 1 session before entry
        })

    confirmed = sorted((c for c in candidates if "Confirmed" in c["strategy_name"]), key=lambda c: c["alpha_score"], reverse=True)
    primary_only = sorted((c for c in candidates if "Primary" in c["strategy_name"]), key=lambda c: c["alpha_score"], reverse=True)
    return confirmed[:MAX_CONFIRMED_SIGNALS] + primary_only[:MAX_PRIMARY_SIGNALS]
