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

def detect_market_structure(df: pd.DataFrame, window: int = 3) -> dict:
    if df is None or len(df) < (window * 2 + 1):
        return {
            "higher_highs": False,
            "higher_lows": False,
            "lower_highs": False,
            "lower_lows": False,
            "trend": "Unknown",
            "confidence": 0.0
        }
        
    highs = df['High'].values
    lows = df['Low'].values
    
    swing_highs = []
    swing_lows = []
    
    for i in range(window, len(df) - window):
        # Check for swing high
        is_swing_high = True
        for j in range(1, window + 1):
            if highs[i] <= highs[i - j] or highs[i] <= highs[i + j]:
                is_swing_high = False
                break
        if is_swing_high:
            swing_highs.append(highs[i])
            
        # Check for swing low
        is_swing_low = True
        for j in range(1, window + 1):
            if lows[i] >= lows[i - j] or lows[i] >= lows[i + j]:
                is_swing_low = False
                break
        if is_swing_low:
            swing_lows.append(lows[i])
            
    # Default state
    hh, hl, lh, ll = False, False, False, False
    trend = "Sideways / Transition"
    confidence = 0.5
    
    if len(swing_highs) >= 2:
        sh1, sh2 = swing_highs[-2], swing_highs[-1]
        hh = sh2 > sh1
        lh = sh2 < sh1
        
    if len(swing_lows) >= 2:
        sl1, sl2 = swing_lows[-2], swing_lows[-1]
        hl = sl2 > sl1
        ll = sl2 < sl1
        
    if hh and hl:
        trend = "Bullish"
        confidence = 0.9
    elif lh and ll:
        trend = "Bearish"
        confidence = 0.9
    elif (hh and ll) or (lh and hl):
        trend = "Sideways / Transition"
        confidence = 0.6
        
    return {
        "higher_highs": bool(hh),
        "higher_lows": bool(hl),
        "lower_highs": bool(lh),
        "lower_lows": bool(ll),
        "trend": trend,
        "confidence": confidence
    }

def detect_market_regime(ind: dict) -> str:
    """Classifies the overall market regime based on ADX, EMAs, and RSI."""
    try:
        ema20 = ind.get("ema", {}).get("20")
        ema50 = ind.get("ema", {}).get("50")
        ema200 = ind.get("ema", {}).get("200")
        adx = ind.get("adx")
        rsi = ind.get("rsi")

        if any(x == UNAVAILABLE or x is None for x in [ema20, ema50, ema200, adx, rsi]):
            return "Unknown Regime"
            
        if ema20 > ema50 > ema200:
            if adx > 25 and rsi > 50:
                return "Strong Bull Trend"
            elif adx < 20:
                return "Correction inside Bull Trend"
            else:
                return "Weak Bull Trend"
        elif ema20 < ema50 < ema200:
            if adx > 25 and rsi < 50:
                return "Strong Bear Trend"
            elif adx < 20:
                return "Recovery inside Bear Trend"
            else:
                return "Weak Bear Trend"
        else:
            if adx < 20:
                return "Sideways"
            else:
                return "Volatile Range"
    except Exception:
        return "Unknown Regime"

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

    try:
        import pandas_ta as ta
    except ImportError:
        print("Warning: pandas-ta not installed. Returning UNAVAILABLE for indicators.")
        return ind

    # Trend: EMA & SMA
    for period in [20, 50, 100, 200]:
        if len(c) >= period:
            ind["ema"][str(period)] = safe_get(ta.ema(c, length=period))
            ind["sma"][str(period)] = safe_get(ta.sma(c, length=period))
        else:
            ind["ema"][str(period)] = UNAVAILABLE
            ind["sma"][str(period)] = UNAVAILABLE

    # Momentum: RSI (14)
    if len(c) >= 15:
        ind["rsi"] = safe_get(ta.rsi(c, length=14))
    else:
        ind["rsi"] = UNAVAILABLE

    # Momentum: MACD
    if len(c) >= 34:
        macd_df = ta.macd(c, fast=12, slow=26, signal=9)
        if macd_df is not None and not macd_df.empty:
            ind["macd"] = {
                "line": safe_get(macd_df.iloc[:, 0]),
                "signal": safe_get(macd_df.iloc[:, 2]),
                "histogram": safe_get(macd_df.iloc[:, 1])
            }
        else:
            ind["macd"] = UNAVAILABLE
    else:
        ind["macd"] = UNAVAILABLE

    # ADX (14)
    if len(c) >= 28:
        adx_df = ta.adx(h, l, c, length=14)
        if adx_df is not None and not adx_df.empty:
            ind["adx"] = safe_get(adx_df.iloc[:, 0])
        else:
            ind["adx"] = UNAVAILABLE
    else:
        ind["adx"] = UNAVAILABLE
    
    # Volatility: ATR (14)
    if len(c) >= 15:
        ind["atr"] = safe_get(ta.atr(h, l, c, length=14))
    else:
        ind["atr"] = UNAVAILABLE

    # Bollinger Bands (20)
    if len(c) >= 20:
        bb_df = ta.bbands(c, length=20, std=2)
        if bb_df is not None and not bb_df.empty:
            ind["bollinger_bands"] = {
                "lower": safe_get(bb_df.iloc[:, 0]),
                "middle": safe_get(bb_df.iloc[:, 1]),
                "upper": safe_get(bb_df.iloc[:, 2])
            }
        else:
            ind["bollinger_bands"] = UNAVAILABLE
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
        
        # Absolute Liquidity metrics
        current_price = float(c.iloc[-1])
        adv_shares = float(vol_sma20.iloc[-1])
        currency_adv = adv_shares * current_price
        
        ind["adv_shares"] = round(adv_shares, 2)
        ind["adv_currency"] = round(currency_adv, 2)
    else:
        ind["relative_volume"] = UNAVAILABLE
        ind["adv_shares"] = UNAVAILABLE
        ind["adv_currency"] = UNAVAILABLE

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

    current_price = float(c.iloc[-1]) if len(c) > 0 else 0.0
    interpretations = {}
    
    regime = detect_market_regime(ind)
    ind["market_regime"] = regime
    interpretations["Market Regime"] = {
        "Value": regime,
        "Interpretation": f"Current market condition is classified as {regime}.",
        "Impact": "Bullish" if "Bull" in regime else "Bearish" if "Bear" in regime else "Neutral"
    }

    # EMA interpretation
    e20, e50, e100, e200 = ind["ema"].get("20"), ind["ema"].get("50"), ind["ema"].get("100"), ind["ema"].get("200")
    if all(x != UNAVAILABLE for x in [e20, e50, e100, e200]):
        val_str = f"EMA20: {e20}, EMA50: {e50}"
        if e20 > e50 and e50 > e100 and e100 > e200:
            interpretations["EMA"] = {"Value": val_str, "Interpretation": "Bullish Uptrend (EMA20 > EMA50 > EMA100 > EMA200)", "Impact": "Bullish"}
        elif e20 < e50 and e50 < e100 and e100 < e200:
            interpretations["EMA"] = {"Value": val_str, "Interpretation": "Bearish Downtrend (EMA20 < EMA50 < EMA100 < EMA200)", "Impact": "Bearish"}
        else:
            interpretations["EMA"] = {"Value": val_str, "Interpretation": "Mixed / Consolidating (Moving averages are crossing or out of strict order)", "Impact": "Neutral"}

    # RSI interpretation
    rsi = ind.get("rsi")
    if isinstance(rsi, (int, float)):
        impact = "Neutral"
        if rsi >= 70:
            interp = "Overbought conditions. Potential for a bearish reversal or pullback."
            impact = "Bearish"
        elif rsi <= 30:
            interp = "Oversold conditions. Potential for a bullish reversal or bounce."
            impact = "Bullish"
        elif 50 < rsi < 70:
            interp = "Bullish momentum. Buyers are in control."
            impact = "Bullish"
        else:
            interp = "Bearish momentum. Sellers are in control."
            impact = "Bearish"
            
        interpretations["RSI"] = {
            "Value": rsi,
            "Interpretation": interp,
            "Impact": impact
        }

    # ADX interpretation
    adx = ind.get("adx")
    if isinstance(adx, (int, float)):
        # Directional Gating
        rsi_val = ind.get("rsi")
        direction = "Neutral"
        if isinstance(rsi_val, (int, float)):
            if rsi_val > 50:
                direction = "Bullish"
            elif rsi_val < 50:
                direction = "Bearish"
                
        impact = f"{direction} Reinforcement" if adx >= 20 and direction != "Neutral" else "Reinforcement"
        
        if adx > 60:
            interp = f"Extremely strong {direction.lower()} trend." if direction != "Neutral" else "Extremely strong trend."
        elif adx >= 40:
            interp = f"Very strong {direction.lower()} trend." if direction != "Neutral" else "Very strong trend."
        elif adx >= 25:
            interp = f"Strong {direction.lower()} trend." if direction != "Neutral" else "Strong trend."
        elif adx >= 20:
            interp = f"Emerging {direction.lower()} trend." if direction != "Neutral" else "Emerging trend."
        else:
            interp = "Weak trend (sideways/choppy)."
            
        interpretations["ADX"] = {
            "Value": round(adx, 2),
            "Interpretation": interp,
            "Impact": impact
        }

    # VWAP interpretation
    vwap = ind.get("vwap")
    if isinstance(vwap, (int, float)) and current_price > 0:
        if current_price > vwap:
            interp = "Price is trading above VWAP, indicating institutional bullish bias."
            impact = "Bullish"
        else:
            interp = "Price is trading below VWAP, indicating institutional bearish bias."
            impact = "Bearish"
            
        interpretations["VWAP"] = {
            "Value": vwap,
            "Interpretation": interp,
            "Impact": impact
        }

    # Bollinger Bands
    bb = ind.get("bollinger_bands")
    if bb != UNAVAILABLE and isinstance(bb, dict):
        upper = bb.get("upper")
        lower = bb.get("lower")
        if upper != UNAVAILABLE and lower != UNAVAILABLE and current_price > 0:
            val_str = f"Upper: {round(upper, 2)} | Lower: {round(lower, 2)}"
            
            band_width = (upper - lower) / lower
            squeeze = band_width < 0.05
            
            impact = "Neutral"
            if squeeze:
                interp = "Band compression (Volatility squeeze) detected; high probability of imminent volatility expansion/breakout."
            elif band_width > 0.15:
                interp = "Wide bands indicating high volatility."
            elif current_price >= upper * 0.995:
                if "Bull" in regime:
                    interp = "Upper band expansion indicating bullish continuation."
                    impact = "Bullish"
                else:
                    interp = "Price riding upper band against the trend, potential for mean reversion."
                    impact = "Bearish"
            elif current_price <= lower * 1.005:
                if "Bear" in regime:
                    interp = "Lower band expansion indicating bearish continuation."
                    impact = "Bearish"
                else:
                    interp = "Lower band touch in non-bearish regime, potential pullback bounce."
                    impact = "Bullish"
            else:
                interp = "Price is within the bands indicating normal volatility."
                
            interpretations["Bollinger Bands"] = {
                "Value": val_str,
                "Interpretation": interp,
                "Impact": impact
            }

    # MACD interpretation
    macd = ind.get("macd")
    if macd != UNAVAILABLE and isinstance(macd, dict):
        m_line, s_line = macd.get("line"), macd.get("signal")
        if isinstance(m_line, (int, float)) and isinstance(s_line, (int, float)):
            val_str = f"Line: {round(m_line, 4)} | Signal: {round(s_line, 4)}"
            impact = "Neutral"
            if m_line > s_line:
                if m_line > 0:
                    interp = "Strong bullish momentum (MACD > Signal, both > 0)."
                    impact = "Bullish"
                else:
                    interp = "Bullish crossover below zero. Potential trend reversal to the upside."
                    impact = "Bullish"
            elif m_line < s_line:
                if m_line < 0:
                    interp = "Strong bearish momentum (MACD < Signal, both < 0)."
                    impact = "Bearish"
                else:
                    interp = "Bearish crossover above zero. Short-term weakness inside longer-term bullish trend."
                    impact = "Bearish"
            else:
                interp = "Neutral. MACD line equals Signal line."
                
            interpretations["MACD"] = {
                "Value": val_str,
                "Interpretation": interp,
                "Impact": impact
            }

    # ATR interpretation
    atr = ind.get("atr")
    if isinstance(atr, (int, float)) and current_price > 0:
        # For ATR we just output it
        interpretations["ATR"] = {
            "Value": round(atr, 2),
            "Interpretation": "High volatility." if atr > (current_price * 0.02) else "Normal volatility.",
            "Impact": "Neutral"
        }

    # Volume interpretation
    rel_vol = ind.get("relative_volume")
    adv_currency = ind.get("adv_currency")
    adv_shares = ind.get("adv_shares")
    
    if isinstance(rel_vol, (int, float)) and not df.empty:
        last_c = df['Close'].iloc[-1]
        last_o = df['Open'].iloc[-1]
        if rel_vol > 1.2:
            if last_c > last_o:
                interp = "Increasing (Volume expanding on up-move)"
                impact = "Bullish"
            else:
                interp = "Increasing (Volume expanding on down-move)"
                impact = "Bearish"
        elif rel_vol < 0.8:
            interp = "Decreasing (Low participation)"
            impact = "Neutral"
        else:
            interp = "Neutral (Average participation)"
            impact = "Neutral"
            
        # Absolute Liquidity Filter
        liquidity_warning = ""
        val_str = f"Rel Vol: {round(rel_vol, 2)}"
        if isinstance(adv_currency, (int, float)) and isinstance(adv_shares, (int, float)):
            val_str += f"<br>ADV: {int(adv_shares/1000)}K<br>T/O: {int(adv_currency/1000000)}M"
            if adv_shares < 100000 or adv_currency < 10000000:
                liquidity_warning = " [SYSTEM WARNING: Fails baseline institutional liquidity filters. Low Tradeability.]"
                
        interpretations["Volume"] = {
            "Value": val_str,
            "Interpretation": interp + liquidity_warning,
            "Impact": impact
        }

    ind["interpretations"] = interpretations
    ind["market_structure"] = detect_market_structure(df)
    
    return ind

def cluster_support_resistance(vision: dict, tech: dict, current_price: float, tolerance_pct: float = 0.015) -> dict:
    levels = []

    if vision:
        for sz in vision.get('support_zones', []):
            try:
                price = float(sz.get('price'))
                if not pd.isna(price) and price > 0:
                    levels.append({"price": price, "source": "Vision Support", "type": "Support"})
            except:
                pass
        for rz in vision.get('resistance_zones', []):
            try:
                price = float(rz.get('price'))
                if not pd.isna(price) and price > 0:
                    levels.append({"price": price, "source": "Vision Resistance", "type": "Resistance"})
            except:
                pass

    pivots = tech.get("pivot_points", {})
    if isinstance(pivots, dict) and "status" not in pivots:
        for k, v in pivots.items():
            if isinstance(v, (int, float)):
                t = "Support" if "S" in k else ("Resistance" if "R" in k else "Pivot")
                levels.append({"price": float(v), "source": f"Pivot {k}", "type": t})

    emas = tech.get("ema", {})
    if isinstance(emas, dict):
        for k, v in emas.items():
            if isinstance(v, (int, float)):
                t = "Support" if v < current_price else "Resistance"
                levels.append({"price": float(v), "source": f"EMA{k}", "type": t})

    vwap = tech.get("vwap")
    if isinstance(vwap, (int, float)):
        t = "Support" if vwap < current_price else "Resistance"
        levels.append({"price": float(vwap), "source": "VWAP", "type": t})

    bb = tech.get("bollinger_bands", {})
    if isinstance(bb, dict) and "status" not in bb:
        upper = bb.get("upper")
        lower = bb.get("lower")
        if isinstance(upper, (int, float)):
            levels.append({"price": float(upper), "source": "BB Upper", "type": "Resistance"})
        if isinstance(lower, (int, float)):
            levels.append({"price": float(lower), "source": "BB Lower", "type": "Support"})

    if not levels:
        return {"support": [], "resistance": []}

    levels.sort(key=lambda x: x["price"])
    clusters = []
    current_cluster = [levels[0]]

    for i in range(1, len(levels)):
        lvl = levels[i]
        avg_cluster_price = sum(x["price"] for x in current_cluster) / len(current_cluster)
        
        if abs(lvl["price"] - avg_cluster_price) / avg_cluster_price <= tolerance_pct:
            current_cluster.append(lvl)
        else:
            clusters.append(current_cluster)
            current_cluster = [lvl]
            
    if current_cluster:
        clusters.append(current_cluster)

    support_clusters = []
    resistance_clusters = []

    for cluster in clusters:
        avg_price = round(sum(x["price"] for x in cluster) / len(cluster), 2)
        sources = [x["source"] for x in cluster]
        
        factors = len(sources)
        if factors >= 3:
            strength = "Strong"
        elif factors == 2:
            strength = "Medium"
        else:
            strength = "Weak"

        cluster_obj = {
            "price": avg_price,
            "strength": strength,
            "factors": sources
        }

        if avg_price <= current_price:
            support_clusters.append(cluster_obj)
        else:
            resistance_clusters.append(cluster_obj)

    support_clusters.sort(key=lambda x: x["price"], reverse=True)
    resistance_clusters.sort(key=lambda x: x["price"])

    return {
        "support": support_clusters,
        "resistance": resistance_clusters
    }
