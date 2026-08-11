import pandas as pd
import numpy as np
import logging
from datetime import date
from typing import List, Dict, Any
from src.data.nse_fetcher import load_nifty500_symbols, fetch_bulk_history
from src.screener import config
import talib
from scipy.signal import argrelextrema

logger = logging.getLogger(__name__)

def evaluate_custom_tools(df: pd.DataFrame, tools: List[str]) -> dict:
    """
    Evaluates a single dataframe against a list of requested technical tools.
    Returns {"passed": bool, "reasons": [], "score": float, "trigger_type": str}
    """
    if df.empty:
        return {"passed": False, "reasons": ["Empty Data"], "score": 0.0, "trigger_type": "None"}
        
    passed = True
    reasons = []
    triggers = []
    score = 0.0
    
    # Simple Close Price mapping for logic
    close = df['Close']
    
    for tool in tools:
        if tool == "Moving Avg":
            # Simple condition: Price > 200 SMA and Price > 50 SMA
            sma200 = close.rolling(200).mean().iloc[-1]
            sma50 = close.rolling(50).mean().iloc[-1]
            curr_price = close.iloc[-1]
            
            if pd.isna(sma200) or pd.isna(sma50) or curr_price < sma200 or curr_price < sma50:
                passed = False
                reasons.append("Failed Moving Avg (Price < 50/200 SMA)")
            else:
                triggers.append("MA Uptrend")
                score += 1.0
                
        elif tool == "RSI":
            # Check RSI Overbought (> 70) or Oversold (< 30)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            curr_rsi = rsi.iloc[-1]
            
            if pd.isna(curr_rsi):
                passed = False
                reasons.append("Failed RSI (Not enough data)")
            elif curr_rsi <= 30:
                triggers.append("RSI Oversold")
                score += 1.0
            elif curr_rsi >= 70:
                triggers.append("RSI Overbought")
                score += 1.0
            else:
                passed = False
                reasons.append(f"Failed RSI (Neutral at {curr_rsi:.1f})")
                
        elif tool == "MACD":
            # MACD Crossover logic (12, 26, 9)
            exp1 = close.ewm(span=12, adjust=False).mean()
            exp2 = close.ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            signal = macd.ewm(span=9, adjust=False).mean()
            hist = macd - signal
            
            # Look for recent bullish crossover (Hist goes from negative to positive)
            if len(hist) > 2 and hist.iloc[-2] < 0 and hist.iloc[-1] > 0:
                triggers.append("MACD Bullish Crossover")
                score += 2.0
            else:
                passed = False
                reasons.append("No MACD Bullish Crossover")
                
        elif tool == "Candle stick patterns":
            if len(df) > 5:
                op = df['Open'].values
                hi = df['High'].values
                lo = df['Low'].values
                cl = df['Close'].values
                
                detected_patterns = []
                if talib.CDLENGULFING(op, hi, lo, cl)[-1] == 100: detected_patterns.append("Bullish Engulfing")
                if talib.CDLENGULFING(op, hi, lo, cl)[-1] == -100: detected_patterns.append("Bearish Engulfing")
                if talib.CDLMORNINGSTAR(op, hi, lo, cl)[-1] > 0: detected_patterns.append("Morning Star")
                if talib.CDLEVENINGSTAR(op, hi, lo, cl)[-1] < 0: detected_patterns.append("Evening Star")
                if talib.CDLHAMMER(op, hi, lo, cl)[-1] > 0: detected_patterns.append("Hammer")
                if talib.CDLSHOOTINGSTAR(op, hi, lo, cl)[-1] < 0: detected_patterns.append("Shooting Star")
                if talib.CDLDOJI(op, hi, lo, cl)[-1] > 0: detected_patterns.append("Doji")
                
                if detected_patterns:
                    triggers.extend(detected_patterns)
                    score += 2.0
                else:
                    passed = False
                    reasons.append("No major candlestick patterns formed")
            else:
                passed = False
                reasons.append("Not enough data for candlesticks")
                
        elif tool == "S&R":
            # Support/Resistance using Donchian Channels (20-day high)
            dc_high = df['High'].rolling(20).max().shift(1)
            if pd.notna(dc_high.iloc[-1]) and df['Close'].iloc[-1] > dc_high.iloc[-1]:
                triggers.append("Resistance Breakout (Donchian)")
                score += 1.5
            else:
                passed = False
                reasons.append("Not breaking S&R")
                
        elif tool == "VWAP":
            # Anchored VWAP approximation (from recent 20-day low)
            if len(df) > 20:
                low_idx = df['Low'].tail(20).idxmin()
                sliced = df.loc[low_idx:]
                if not sliced.empty:
                    vwap = (sliced['Volume'] * ((sliced['High'] + sliced['Low'] + sliced['Close']) / 3)).sum() / sliced['Volume'].sum()
                    if close.iloc[-1] > vwap:
                        triggers.append("Above AVWAP")
                        score += 1.0
                    else:
                        passed = False
                        reasons.append("Below AVWAP")
                else:
                    passed = False
                    reasons.append("AVWAP failed")
            else:
                passed = False
                reasons.append("Not enough data for AVWAP")
                
        elif tool == "Chart Patterns":
            # Algorithmic Chart Patterns using SciPy extrema
            if len(df) > 30:
                # Find local minima (troughs) and maxima (peaks) over last 30 days
                recent_close = close.tail(30).values
                minima_idx = argrelextrema(recent_close, np.less, order=3)[0]
                maxima_idx = argrelextrema(recent_close, np.greater, order=3)[0]
                
                patterns = []
                # Double Bottom (W pattern): Two distinct minima at roughly same level
                if len(minima_idx) >= 2:
                    last_two_min = recent_close[minima_idx[-2:]]
                    if abs(last_two_min[0] - last_two_min[1]) / last_two_min[0] < 0.03:
                        patterns.append("Double Bottom")
                        
                # Double Top (M pattern): Two distinct maxima at roughly same level
                if len(maxima_idx) >= 2:
                    last_two_max = recent_close[maxima_idx[-2:]]
                    if abs(last_two_max[0] - last_two_max[1]) / last_two_max[0] < 0.03:
                        patterns.append("Double Top")
                        
                # Head & Shoulders Top: 3 maxima, middle is highest
                if len(maxima_idx) >= 3:
                    last_three_max = recent_close[maxima_idx[-3:]]
                    if last_three_max[1] > last_three_max[0] and last_three_max[1] > last_three_max[2]:
                        patterns.append("Head & Shoulders Top")
                        
                if patterns:
                    triggers.extend(patterns)
                    score += 2.5
                else:
                    passed = False
                    reasons.append("No classical chart patterns detected")
            else:
                passed = False
                reasons.append("Not enough data for chart patterns")
            
        elif tool == "Market Structure":
            # Higher Highs, Higher Lows (Simple 5-day check)
            if len(df) > 10:
                curr_high = df['High'].iloc[-1]
                prev_high = df['High'].iloc[-5:-1].max()
                if curr_high > prev_high:
                    triggers.append("Higher High Structure")
                    score += 1.0
                else:
                    passed = False
                    reasons.append("Failed Market Structure HH")
            else:
                passed = False
                reasons.append("Not enough data")
                
        elif tool == "Trendline":
            passed = False
            reasons.append("Trendline mapping WIP")
            
        if not passed:
            break  # Fast fail for AND logic
            
    if passed and len(tools) == 0:
        passed = False
        reasons.append("No tools selected")
        
    return {
        "passed": passed,
        "reasons": reasons,
        "score": score,
        "trigger_type": " + ".join(triggers) if triggers else "None"
    }

def run_custom_screener(
    as_of_date: date = None, 
    trading_tools: List[str] = None, 
    risk_management: str = "ATR 1.5", 
    ai_logic_prompt: str = None,
    gemini_api_key: str = None,
    top_n: int = 20, 
    progress_callback=None
) -> Dict[str, Any]:
    if as_of_date is None:
        as_of_date = date.today()
    if trading_tools is None:
        trading_tools = []
        
    def log_progress(msg, level="INFO"):
        if level == "WARNING":
            logger.warning(msg)
        elif level == "ERROR":
            logger.error(msg)
        else:
            logger.info(msg)
        if progress_callback:
            progress_callback(msg, level)
            
    log_progress(f"Starting Custom Strategy Builder with Tools: {trading_tools}")
    
    # 1. Generate AI Logic if provided
    has_ai_logic = False
    if ai_logic_prompt:
        log_progress("Generating dynamic AI Python logic...")
        try:
            from src.services.ai_coder import generate_pandas_logic
            generated_code = generate_pandas_logic(ai_logic_prompt, gemini_api_key)
            log_progress(f"AI generated code:\n{generated_code}")
            
            # Use a secure isolated namespace
            isolated_globals = {}
            exec(generated_code, isolated_globals)
            if "custom_ai_eval" not in isolated_globals:
                raise ValueError("LLM did not output a custom_ai_eval function.")
                
            custom_ai_eval_func = isolated_globals["custom_ai_eval"]
            has_ai_logic = True
            log_progress("AI Logic successfully compiled and loaded into memory.")
        except Exception as e:
            log_progress(f"Failed to compile AI logic: {e}", level="ERROR")
            # We don't crash, we just won't execute AI logic.
    
    universe = load_nifty500_symbols()
    log_progress(f"Loaded {len(universe)} symbols from NIFTY 500.")
    
    # 2. Fetch Historical Data (Batch)
    log_progress(f"Fetching bulk history (lookback=300 days)...")
    bulk_data = fetch_bulk_history(universe, as_of_date, lookback_days=300)
    
    candidates = []
    
    log_progress("Evaluating stocks against custom tools...")
    for symbol, df in bulk_data.items():
        if df.empty:
            continue
            
        eval_result = evaluate_custom_tools(df, trading_tools)
        
        # Apply AI Logic dynamically
        ai_passed = True
        if has_ai_logic:
            try:
                ai_res = custom_ai_eval_func(df)
                if not ai_res.get("passed", False):
                    ai_passed = False
                    # Optionally append reasons if we want to log them
            except Exception as e:
                # Catch hallucinations (e.g. KeyError) gracefully
                ai_passed = False
                logger.debug(f"AI Logic crashed on {symbol}: {e}")
                
        if eval_result["passed"] and ai_passed:
            entry_price = df['Close'].iloc[-1]
            atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
            
            # Parse Risk Management
            # e.g., "ATR 1.5" or "PCT 5.0"
            risk_parts = risk_management.split(" ")
            if len(risk_parts) == 2 and risk_parts[0].upper() == "ATR":
                try:
                    mult = float(risk_parts[1])
                    stop_loss = entry_price - (mult * atr) if pd.notna(atr) else entry_price * 0.95
                except ValueError:
                    stop_loss = entry_price - (1.5 * atr) if pd.notna(atr) else entry_price * 0.95
            elif len(risk_parts) == 2 and risk_parts[0].upper() == "PCT":
                try:
                    pct = float(risk_parts[1]) / 100.0
                    stop_loss = entry_price * (1 - pct)
                except ValueError:
                    stop_loss = entry_price * 0.95
            else:
                # Default fallback
                stop_loss = entry_price - (1.5 * atr) if pd.notna(atr) else entry_price * 0.95
                
            risk_amount = entry_price - stop_loss
            target = entry_price + (2.0 * risk_amount) # Default 1:2 RR
            
            # Default Position Sizing (Assuming ₹1,00,000 account, 2% risk = ₹2000 risk per trade)
            risk_per_trade = 2000
            qty = max(1, int(risk_per_trade / risk_amount)) if risk_amount > 0 else 0
            
            candidates.append({
                "symbol": symbol,
                "score": eval_result["score"],
                "trigger_type": eval_result["trigger_type"],
                "entry_price": round(entry_price, 2),
                "target": round(target, 2),
                "stop_loss": round(stop_loss, 2),
                "position_size": qty,
                "trend_status": "Custom Match",
                "peers": []  # Empty for custom for now
            })
            
    # Sort by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    top_candidates = candidates[:top_n]
    
    log_progress("=========================================")
    log_progress(f"Custom Strategy Found {len(top_candidates)} Matches.")
    log_progress("=========================================")
    
    return {
        "candidates": top_candidates,
        "watchlist": [],
        "regime": "CUSTOM"
    }
