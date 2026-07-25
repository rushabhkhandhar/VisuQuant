import pandas as pd
import numpy as np
import math

UNAVAILABLE = {"status": "Unavailable", "reason": "Insufficient historical candles"}

def safe_get(val):
    if val is None:
        return UNAVAILABLE
        
    if isinstance(val, pd.Series):
        if len(val) == 0:
            return UNAVAILABLE
        val = val.iloc[-1]
        
    if pd.isna(val):
        return UNAVAILABLE
        
    if isinstance(val, (np.float64, np.int64, np.float32, np.int32)):
        val = val.item()
        
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return UNAVAILABLE
            
    try:
        return round(float(val), 4)
    except (ValueError, TypeError):
        return UNAVAILABLE

def calculate_technical_indicators(df: pd.DataFrame) -> dict:
    if df is None or df.empty or len(df) < 2:
        return {}

    # Ensure required columns exist
    required = ['Open', 'High', 'Low', 'Close', 'Volume']
    for col in required:
        if col not in df.columns:
            # Try lowercase
            if col.lower() in df.columns:
                df[col] = df[col.lower()]
            else:
                return {} # Missing required data
                
    # Sort chronologically if a Date index exists
    if 'Date' in df.columns or df.index.name == 'Date':
        if 'Date' in df.columns:
            df = df.sort_values('Date').reset_index(drop=True)
        else:
            df = df.sort_index()

    c = df['Close']
    h = df['High']
    l = df['Low']
    v = df['Volume']

    ind = {
        "ema": {},
        "sma": {},
        "macd": {},
        "bollinger_bands": {},
        "statistics": {},
        "pivot_points": UNAVAILABLE,
        "fibonacci": UNAVAILABLE
    }

    # Trend: EMA & SMA
    for period in [20, 50, 100, 200]:
        if len(c) >= period:
            ind["ema"][str(period)] = safe_get(c.ewm(span=period, adjust=False).mean())
            ind["sma"][str(period)] = safe_get(c.rolling(window=period).mean())
        else:
            ind["ema"][str(period)] = UNAVAILABLE
            ind["sma"][str(period)] = UNAVAILABLE

    # Momentum: RSI (14)
    if len(c) >= 15:
        delta = c.diff()
        gain = delta.where(delta > 0, 0).ewm(alpha=1/14, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(alpha=1/14, adjust=False).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        ind["rsi"] = safe_get(rsi)
    else:
        ind["rsi"] = UNAVAILABLE

    # Momentum: MACD
    if len(c) >= 26:
        ema12 = c.ewm(span=12, adjust=False).mean()
        ema26 = c.ewm(span=26, adjust=False).mean()
        macd_line = ema12 - ema26
        signal_line = macd_line.ewm(span=9, adjust=False).mean()
        hist = macd_line - signal_line
        ind["macd"] = {
            "line": safe_get(macd_line),
            "signal": safe_get(signal_line),
            "histogram": safe_get(hist)
        }
    else:
        ind["macd"] = UNAVAILABLE

    # ADX (14)
    if len(c) >= 15:
        prev_c = c.shift(1)
        prev_h = h.shift(1)
        prev_l = l.shift(1)
        
        tr1 = h - l
        tr2 = (h - prev_c).abs()
        tr3 = (l - prev_c).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        up_move = h - prev_h
        down_move = prev_l - l
        
        plus_dm = pd.Series(np.where((up_move > down_move) & (up_move > 0), up_move, 0.0), index=c.index)
        minus_dm = pd.Series(np.where((down_move > up_move) & (down_move > 0), down_move, 0.0), index=c.index)
        
        atr_14 = tr.ewm(alpha=1/14, adjust=False).mean()
        plus_di = 100 * (plus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_14)
        minus_di = 100 * (minus_dm.ewm(alpha=1/14, adjust=False).mean() / atr_14)
        
        dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di)
        adx = dx.ewm(alpha=1/14, adjust=False).mean()
        
        ind["adx"] = safe_get(adx)
    else:
        ind["adx"] = UNAVAILABLE
    
    # Volatility: ATR (14)
    if len(c) >= 2:
        prev_c = c.shift(1)
        tr1 = h - l
        tr2 = (h - prev_c).abs()
        tr3 = (l - prev_c).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.ewm(alpha=1/14, adjust=False).mean()
        ind["atr"] = safe_get(atr)
    else:
        ind["atr"] = UNAVAILABLE

    # Bollinger Bands (20)
    if len(c) >= 20:
        sma20 = c.rolling(20).mean()
        std20 = c.rolling(20).std()
        ind["bollinger_bands"] = {
            "middle": safe_get(sma20),
            "upper": safe_get(sma20 + 2*std20),
            "lower": safe_get(sma20 - 2*std20)
        }
    else:
        ind["bollinger_bands"] = UNAVAILABLE

    # VWAP (Cumulative for the loaded period)
    if len(c) > 0:
        typical_price = (h + l + c) / 3
        vwap = (typical_price * v).cumsum() / v.cumsum()
        ind["vwap"] = safe_get(vwap)
    else:
        ind["vwap"] = UNAVAILABLE

    # OBV
    if len(c) > 0:
        direction = np.sign(c.diff())
        direction.iloc[0] = 1
        obv = (direction * v).cumsum()
        ind["obv"] = safe_get(obv)
    else:
        ind["obv"] = UNAVAILABLE

    # Relative Volume (Ratio of current volume to 20-day SMA of volume)
    if len(v) >= 20:
        vol_sma20 = v.rolling(20).mean()
        rel_vol = v / vol_sma20
        ind["relative_volume"] = safe_get(rel_vol)
    else:
        ind["relative_volume"] = UNAVAILABLE

    # Pivot Points (Standard Daily based on previous day)
    if len(c) >= 2:
        prev_h = h.iloc[-2]
        prev_l = l.iloc[-2]
        prev_c = c.iloc[-2]
        p = (prev_h + prev_l + prev_c) / 3
        ind["pivot_points"] = {
            "P": round(p, 2),
            "R1": round(2*p - prev_l, 2),
            "S1": round(2*p - prev_h, 2),
            "R2": round(p + (prev_h - prev_l), 2),
            "S2": round(p - (prev_h - prev_l), 2)
        }
    else:
        ind["pivot_points"] = UNAVAILABLE

    # Swing High / Low (Local extrema over last 20 days)
    if len(c) >= 20:
        last20_h = h.tail(20).max()
        last20_l = l.tail(20).min()
        ind["swing_high"] = float(last20_h)
        ind["swing_low"] = float(last20_l)
    else:
        ind["swing_high"] = UNAVAILABLE
        ind["swing_low"] = UNAVAILABLE

    # Fibonacci (Recent swing high/low)
    if ind["swing_high"] != UNAVAILABLE and ind["swing_low"] != UNAVAILABLE:
        diff = ind["swing_high"] - ind["swing_low"]
        ind["fibonacci"] = {
            "0.0": ind["swing_low"],
            "0.236": round(ind["swing_low"] + diff * 0.236, 2),
            "0.382": round(ind["swing_low"] + diff * 0.382, 2),
            "0.500": round(ind["swing_low"] + diff * 0.500, 2),
            "0.618": round(ind["swing_low"] + diff * 0.618, 2),
            "1.0": ind["swing_high"]
        }
    else:
        ind["fibonacci"] = UNAVAILABLE

    # Statistics
    if len(c) > 0:
        ind["statistics"]["average_volume"] = safe_get(v.mean())
        if len(c) >= 20:
            ind["statistics"]["20_day_high"] = float(h.tail(20).max())
            ind["statistics"]["20_day_low"] = float(l.tail(20).min())
        else:
            ind["statistics"]["20_day_high"] = UNAVAILABLE
            ind["statistics"]["20_day_low"] = UNAVAILABLE
            
        if len(c) >= 252: # Approx 52 weeks
            ind["statistics"]["52_week_high"] = float(h.tail(252).max())
            ind["statistics"]["52_week_low"] = float(l.tail(252).min())
        else:
            ind["statistics"]["52_week_high"] = UNAVAILABLE
            ind["statistics"]["52_week_low"] = UNAVAILABLE
    else:
        ind["statistics"]["average_volume"] = UNAVAILABLE
        ind["statistics"]["20_day_high"] = UNAVAILABLE
        ind["statistics"]["20_day_low"] = UNAVAILABLE
        ind["statistics"]["52_week_high"] = UNAVAILABLE
        ind["statistics"]["52_week_low"] = UNAVAILABLE

    # Interpretations (Deterministic String Logic)
    interpretations = {
        "ema_trend": "Unknown",
        "rsi_condition": "Unknown",
        "macd_condition": "Unknown"
    }

    # EMA interpretation
    e20, e50, e100, e200 = ind["ema"].get("20"), ind["ema"].get("50"), ind["ema"].get("100"), ind["ema"].get("200")
    if all(x != UNAVAILABLE for x in [e20, e50, e100, e200]):
        if e20 > e50 and e50 > e100 and e100 > e200:
            interpretations["ema_trend"] = "Bullish Uptrend (EMA20 > EMA50 > EMA100 > EMA200)"
        elif e20 < e50 and e50 < e100 and e100 < e200:
            interpretations["ema_trend"] = "Bearish Downtrend (EMA20 < EMA50 < EMA100 < EMA200)"
        else:
            interpretations["ema_trend"] = "Mixed / Consolidating (Moving averages are crossing or out of strict order)"

    # RSI interpretation
    rsi = ind.get("rsi")
    if rsi != UNAVAILABLE:
        if rsi >= 70:
            interpretations["rsi_condition"] = f"Overbought ({rsi})"
        elif rsi <= 30:
            interpretations["rsi_condition"] = f"Oversold ({rsi})"
        elif 50 < rsi < 70:
            interpretations["rsi_condition"] = f"Bullish Momentum ({rsi})"
        else:
            interpretations["rsi_condition"] = f"Bearish Momentum ({rsi})"

    # MACD interpretation
    macd = ind.get("macd")
    if macd != UNAVAILABLE and isinstance(macd, dict):
        m_line, s_line = macd.get("line"), macd.get("signal")
        if m_line != UNAVAILABLE and s_line != UNAVAILABLE:
            if m_line > s_line:
                if m_line > 0:
                    interpretations["macd_condition"] = "Strong Bullish (Line > Signal, both > 0)"
                else:
                    interpretations["macd_condition"] = "Bullish Crossover (Line > Signal, below 0)"
            elif m_line < s_line:
                if m_line < 0:
                    interpretations["macd_condition"] = "Strong Bearish (Line < Signal, both < 0)"
                else:
                    interpretations["macd_condition"] = "Bearish Crossover (Line < Signal, above 0)"
            else:
                interpretations["macd_condition"] = "Neutral (Line == Signal)"

    ind["interpretations"] = interpretations

    return ind
