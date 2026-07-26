import os
import json
import base64
import pandas as pd
import ollama
from playwright.sync_api import sync_playwright

from src.state import TradingState
from src.scraper import fetch_nse_data

def node_capture_chart(state: TradingState) -> dict:
    ticker = state["ticker"]
    print(f"[{ticker}] Capturing TradingView chart...")
    
    b64_image = None
    
    # Use playwright to capture the chart
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        
        urls_to_try = [
            f"https://in.tradingview.com/chart/?symbol=NSE%3A{ticker}",
            f"https://www.google.com/finance/quote/{ticker}:NSE"
        ]
        
        for url in urls_to_try:
            try:
                print(f"[{ticker}] Attempting to capture chart from {url}...")
                page.goto(url, wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(5000)
                screenshot_bytes = page.screenshot()
                b64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
                print(f"[{ticker}] Chart captured successfully as base64 string.")
                break
            except Exception as e:
                print(f"[{ticker}] Failed to capture chart from {url}: {e}")
                
        browser.close()
            
    return {"chart_image_base64": b64_image}

def node_run_nse_scraper(state: TradingState) -> dict:
    ticker = state["ticker"]
    data = fetch_nse_data(ticker)
    return {"scraped_data": data}

def node_vision_analysis(state: TradingState) -> dict:
    ticker = state["ticker"]
    chart_image_base64 = state.get("chart_image_base64")
    
    if not chart_image_base64:
        print(f"[{ticker}] No chart image found. Skipping vision analysis.")
        return {"vision_features": None, "vision_analysis": None}

    print(f"[{ticker}] Running vision feature extraction (interpreting base64 image)...")

    prompt = f"""
    You are a computer vision model performing feature extraction on a TradingView chart.

    Your task is NOT to perform trading analysis.
    Your task is ONLY to extract observable visual information.

    Rules:
    - Return VALID JSON only. No markdown. No explanations.
    - No BUY/SELL/HOLD recommendation.
    - Do not estimate indicators that are not visibly plotted.
    - If something is not visible, return null.
    - Never invent values. Never hallucinate certainty. If confidence is low, state uncertainty (lower the confidence score).

    NUMERICAL VALUES RULE (CRITICAL):
    Every numerical value extracted from the chart (like support and resistance prices) MUST include `confidence`, `source`, and `visibility`. 
    Only output exact prices when clearly visible on the y-axis or explicitly labeled. 
    Otherwise, return `null` for the price, provide a description (e.g., 'Approximate support zone'), and lower the confidence. Never hallucinate exact numbers.

    INTERNAL CONSISTENCY VALIDATION (CRITICAL):
    You must validate the relationships between: Trend, Market Structure, Swing Highs/Lows, Trendlines, and Channels.
    - A "Downtrend" MUST be logically compatible with Lower Highs and Lower Lows.
    - An "Uptrend" MUST be logically compatible with Higher Highs and Higher Lows.
    - A "Sideways" trend must not claim aggressively trending structures.
    - Hierarchical Context (CRITICAL): Prioritize Market Structure over Channels and Trendlines.
      - If Market Structure is Bullish (Higher Highs, Higher Lows), a Falling Channel is a "Corrective Pullback", NOT a "Bearish Trend".
      - If Market Structure is Bearish (Lower Highs, Lower Lows), a Rising Channel is a "Bearish Rally", NOT a "Bullish Trend".
    - If you detect contradictions in your own visual assessment (e.g. you see a Downtrend but the structure is Higher Highs), you MUST NOT output the contradiction. Instead, resolve the context (e.g. "Short-term pullback in a long-term bullish trend").
    - If Market Structure is clearly identified, Trend Confidence cannot be 'Unknown' or low.

    Extract:
    1. Trend (Direction and Visual confidence 0-100)
    3. Support Zones (Approximate price, Strength)
    4. Resistance Zones (Approximate price, Strength)
    5. Chart Patterns & Candlestick Patterns. For candlesticks, use STRICT terminology:
       - Hammer = Bullish
       - Hanging Man = Bearish
       - Inverted Hammer = Bullish
       - Shooting Star = Bearish
       Do NOT invent ambiguous names (e.g. "Bearish Hammer").
    6. Trendlines (Type, touches, broken)
    7. Channels
    8. Visible Indicators (EMA, VWAP, Bollinger, RSI, MACD, Volume)
    9. Events (Breakout, Breakdown, Retest, Gap Up, Gap Down)
    10. Volume (Increasing, Decreasing, Spike)

    RETURN EXACTLY THIS JSON SCHEMA:
    {{
      "consistency_status": "PASSED | FAILED",
      "warnings": [],
      "trend": {{
        "long_term_trend": "Bullish | Bearish | Sideways | Unknown",
        "medium_term_trend": "Bullish | Bearish | Sideways | Unknown",
        "short_term_structure": "Impulse | Pullback | Consolidation | Breakdown",
        "current_channel": "Rising | Falling | Horizontal | None",
        "overall_interpretation": "Provide a 1-sentence market context description without listing conflicting facts. E.g. 'The stock remains in a long-term bullish trend but is currently undergoing a short-term pullback inside a falling corrective channel.'",
        "confidence": 0
      }},
      "support_zones": [
        {{
          "price": null,
          "description": "Approximate support zone",
          "confidence": 0.0,
          "source": "Chart label | Visual estimation | Indicator",
          "visibility": "Clear | Obscured | Implied",
          "strength": "Strong | Medium | Weak"
        }}
      ],
      "resistance_zones": [
        {{
          "price": null,
          "description": "Approximate resistance zone",
          "confidence": 0.0,
          "source": "Chart label | Visual estimation | Indicator",
          "visibility": "Clear | Obscured | Implied",
          "strength": "Strong | Medium | Weak"
        }}
      ],
      "patterns": {{
        "chart": [],
        "candlestick": [
          {{
            "pattern_name": "Hammer | Hanging Man | Inverted Hammer | Shooting Star | Doji | Engulfing",
            "sentiment": "Bullish | Bearish | Neutral",
            "confidence": 0.0
          }}
        ]
      }},
      "trendlines": [
        {{
          "type": "Ascending | Descending | Horizontal",
          "touches": 0,
          "broken": false
        }}
      ],
      "channels": [
        {{
          "type": "Rising | Falling | Horizontal"
        }}
      ],
      "visible_indicators": {{
        "ema20": false,
        "ema50": false,
        "ema100": false,
        "ema200": false,
        "vwap": false,
        "bollinger_bands": false,
        "rsi": false,
        "macd": false,
        "volume": false,
        "fibonacci_overlay": false
      }},
      "events": {{
        "breakout": false,
        "breakdown": false,
        "retest": false,
        "gap_up": false,
        "gap_down": false
      }},
      "volume": {{
        "trend": "Increasing | Decreasing | Neutral | Unknown",
        "spike": false
      }}
    }}
    """
    
    parsed_json = None
    raw_analysis = ""
    
    # Try up to 2 times to get valid JSON
    for attempt in range(2):
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [chart_image_base64]
            }],
            options={'temperature': 0.0}
        )
        raw_analysis = response['message']['content']
        
        # Robust parsing (strip markdown tags if model ignored instructions)
        cleaned_str = raw_analysis.strip()
        if cleaned_str.startswith("```json"):
            cleaned_str = cleaned_str[7:]
        elif cleaned_str.startswith("```"):
            cleaned_str = cleaned_str[3:]
            
        if cleaned_str.endswith("```"):
            cleaned_str = cleaned_str[:-3]
            
        cleaned_str = cleaned_str.strip()
        
        try:
            parsed_json = json.loads(cleaned_str)
            
            # Post-processing: Filter low confidence patterns and trends
            if "patterns" in parsed_json:
                for p_type in ["candlestick", "chart"]:
                    if p_type in parsed_json["patterns"]:
                        valid_patterns = []
                        for p in parsed_json["patterns"][p_type]:
                            conf = p.get("confidence", 0.0)
                            try:
                                conf = float(conf)
                            except:
                                conf = 0.0
                            
                            if conf < 0.30:
                                continue
                            elif conf <= 0.60:
                                p["pattern_name"] = f"{p.get('pattern_name', 'Unknown')} (Weak)"
                            else:
                                p["pattern_name"] = f"{p.get('pattern_name', 'Unknown')} (Confirmed)"
                            valid_patterns.append(p)
                        parsed_json["patterns"][p_type] = valid_patterns
            
            if "trendlines" in parsed_json:
                for tl in parsed_json["trendlines"]:
                    conf = tl.get("confidence", 0.0)
                    try:
                        conf = float(conf)
                    except:
                        conf = 0.0
                    
                    if conf < 0.30:
                        tl["type"] = "Inconclusive"
                        
            break
        except json.JSONDecodeError:
            print(f"[{ticker}] Warning: Failed to parse JSON on attempt {attempt+1}. Retrying...")
            continue
            
    if parsed_json is None:
        parsed_json = {
            "error": "Failed to parse JSON output after retries.",
            "raw_output": raw_analysis
        }
        
    print(f"[{ticker}] Vision feature extraction complete.")
    
    return {
        "vision_features": parsed_json,
        "vision_analysis": json.dumps(parsed_json, indent=2) # Backward compatibility for downstream nodes
    }

from src.quant_calculations import calculate_technical_indicators

def node_quantitative_analysis(state: TradingState) -> dict:
    ticker = state["ticker"]
    scraped_data = state.get("scraped_data", {})
    
    print(f"[{ticker}] Running quantitative analysis...")
    
    # Assumption: scraped_data contains a key 'history' or 'historical_data' 
    # which is a list of OHLCV dictionaries.
    df = pd.DataFrame()
    if isinstance(scraped_data, dict):
        if "history" in scraped_data:
            df = pd.DataFrame(scraped_data["history"])
        elif "historical_data" in scraped_data:
            df = pd.DataFrame(scraped_data["historical_data"])
        elif "data" in scraped_data:
            df = pd.DataFrame(scraped_data["data"])
    elif isinstance(scraped_data, list):
        df = pd.DataFrame(scraped_data)
        
    indicators = calculate_technical_indicators(df)
    
    print(f"[{ticker}] Quantitative analysis complete.")
    return {"technical_indicators": indicators}

def node_trend_engine(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_features = state.get("vision_features", {})
    technical_indicators = state.get("technical_indicators", {})
    
    print(f"[{ticker}] Running unified trend engine...")
    
    # Extract components
    vision_trend = vision_features.get("trend", {})
    vision_direction = vision_trend.get("direction", "Unknown")
    vision_conf = float(vision_trend.get("confidence", 0.0))
    
    market_structure = technical_indicators.get("market_structure", {})
    ms_trend = market_structure.get("trend", "Unknown")
    ms_conf = float(market_structure.get("confidence", 0.5))
    
    interpretations = technical_indicators.get("interpretations", {})
    ema_interp = interpretations.get("EMA", {})
    ema_impact = ema_interp.get("Impact", "Neutral")
    
    adx_interp = interpretations.get("ADX", {})
    adx_val = adx_interp.get("Value", 0)
    adx_strength = "Weak"
    if adx_val >= 25:
        adx_strength = "Strong"
        
    # Aggregate
    bull_score = 0.0
    bear_score = 0.0
    
    if vision_direction == "Uptrend":
        bull_score += vision_conf
    elif vision_direction == "Downtrend":
        bear_score += vision_conf
        
    if ms_trend == "Bullish":
        bull_score += ms_conf
    elif ms_trend == "Bearish":
        bear_score += ms_conf
        
    if ema_impact == "Bullish":
        bull_score += 0.8
    elif ema_impact == "Bearish":
        bear_score += 0.8
        
    # Determine Unified Trend
    trend_direction = "Sideways / Transition"
    confidence = 0.5
    
    if bull_score > bear_score + 0.5:
        trend_direction = "Bullish"
        confidence = min(1.0, bull_score / 3.0)
    elif bear_score > bull_score + 0.5:
        trend_direction = "Bearish"
        confidence = min(1.0, bear_score / 3.0)
    else:
        trend_direction = "Sideways / Transition"
        confidence = min(1.0, (bull_score + bear_score) / 4.0)
        
    # Boost confidence if ADX is strong
    if adx_strength == "Strong" and trend_direction != "Sideways / Transition":
        confidence = min(1.0, confidence + 0.2)
        
    evidence = []
    evidence.append(f"Market Structure: {ms_trend}")
    evidence.append(f"EMA Alignment: {ema_impact}")
    evidence.append(f"Vision Detection: {vision_direction}")
    evidence.append(f"ADX Strength: {adx_val} ({adx_strength})")
        
    unified_trend = {
        "direction": trend_direction,
        "confidence": round(confidence, 2),
        "supporting_evidence": evidence
    }
    
    print(f"[{ticker}] Unified trend engine complete: {trend_direction} (Conf: {round(confidence, 2)})")
    
    return {"unified_trend": unified_trend}

def node_confluence_engine(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_features = state.get("vision_features", {})
    technical_indicators = state.get("technical_indicators", {})
    unified_trend = state.get("unified_trend", {})
    
    print(f"[{ticker}] Running confluence engine (evidence synthesis)...")
    
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": technical_indicators.get("interpretations", {}),
        "pivot_points": technical_indicators.get("pivot_points", {})
    }
    
    prompt = f"""
    You are an expert quantitative trading engine for {ticker}.
    Your objective is to identify confluences and contradictions between visual features and technical indicators.
    
    Unified Trend Engine Output:
    {json.dumps(unified_trend)}
    
    Available Visual Features:
    {json.dumps(vision_features)}
    
    Available Technical Indicators (Quantitative):
    {json.dumps(simplified_quantitative)}
    
    RULES:
    1. Base all trend direction conclusions solely on the "Unified Trend Engine Output". Do not re-evaluate the trend independently.
    2. Base all indicator interpretations strictly on the exact strings provided in the "interpretations" dictionary. Never reinterpret raw indicators (e.g. do not recalculate MACD crossovers).
    3. Generate summary bullet points that are directly sourced from the provided "interpretations".
    4. EXPLANATION LAYER: You must provide an institutional-style `explanation` for each section, contextualizing the findings. DO NOT output logically impossible sentences (e.g. "Downtrend but Higher Highs observed"). Instead, use comparative analysis: "The visual model suggests X, while quantitative identifies Y, indicating disagreement."
    5. VOLUME INHERITANCE: If quantitative volume interpretation exists, the volume status MUST NOT be 'Unknown'. It MUST inherit the quantitative classification (e.g. 'Decreasing', 'Increasing', 'Neutral').
    
    - Return VALID JSON only.
    - No markdown.
    - No explanations outside JSON.
    - No BUY/SELL/HOLD recommendation.
    - No stop-loss or target prices.
    - Do not calculate indicators.
    - Do not estimate missing values.
    - Numerical fields (like confidence or scores) MUST be single numbers (e.g. 0.8), never mathematical expressions (like 40/50).
    - If a field does not exist inside technical indicators or vision features, explicitly list it inside the missing_data field.
    - Never invent values or hallucinate missing information.
    
    WEIGHTED SCORING (CRITICAL):
    You must calculate an overall confluence score strictly based on these maximum weights (Total = 100):
    - Trend = 30
    - Momentum = 20
    - Support & Resistance = 20
    - Volume = 15
    - Patterns = 15
    
    If an entire category is unavailable (e.g. Volume is unavailable), you MUST reduce confidence and heavily penalize the score for that category. Do NOT assign full marks for missing data.
    Explain your calculation for each category within its respective "reason" field.

    Available Visual Features:
    {json.dumps(vision_features)}

    Available Technical Indicators (Quantitative):
    {json.dumps(simplified_quantitative)}

    Compare the following whenever available. CRITICAL: For technical indicators, do NOT interpret raw numbers. You MUST use the deterministic string values provided in the `interpretations` object inside the quantitative JSON!
    - Trend (Vision vs Quantitative `EMA`)
    - Momentum (Quantitative `RSI` and `MACD`)
    - Volume (Relative Volume/OBV/VWAP)
    - Support & Resistance (Vision vs Pivot Points/Swing High/Low/Fibonacci)
    - Patterns (Chart/Candlestick)
    - Events (Breakout/Breakdown/Retest/Gap)
    - Market Structure (Higher Highs/Lows)

    RETURN EXACTLY THIS JSON SCHEMA:
    {{
        "trend": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "explanation": "Institutional-grade explanation combining visual and quantitative findings..."
        }},
        "momentum": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown | Bullish | Bearish",
            "confidence": 0,
            "explanation": "Institutional-grade explanation..."
        }},
        "volume": {{
            "status": "Increasing | Decreasing | Neutral | Breakout Confirmation | Distribution | Accumulation",
            "confidence": 0,
            "explanation": "Institutional-grade explanation inheriting the quantitative state..."
        }},
        "support_resistance": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "explanation": "Institutional-grade explanation..."
        }},
        "patterns": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "explanation": "Institutional-grade explanation..."
        }},
        "contradictions": [
            {{
                "category": "...",
                "reason": "..."
            }}
        ],
        "missing_data": [
            "..."
        ],
        "scores": {{
            "trend": 0,
            "momentum": 0,
            "support_resistance": 0,
            "volume": 0,
            "patterns": 0
        }},
        "overall_score": 0,
        "overall_confluence": {{
            "score": 0,
            "strength": "Strong | Moderate | Weak | Unknown"
        }}
    }}
    """
    
    parsed_json = None
    raw_analysis = ""
    
    for attempt in range(2):
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt
            }],
            options={'temperature': 0.0}
        )
        raw_analysis = response['message']['content']
        
        # Robust parsing
        cleaned_str = raw_analysis.strip()
        if cleaned_str.startswith("```json"):
            cleaned_str = cleaned_str[7:]
        elif cleaned_str.startswith("```"):
            cleaned_str = cleaned_str[3:]
            
        if cleaned_str.endswith("```"):
            cleaned_str = cleaned_str[:-3]
            
        cleaned_str = cleaned_str.strip()
        
        try:
            parsed_json = json.loads(cleaned_str)
            break
        except json.JSONDecodeError:
            print(f"[{ticker}] Warning: Failed to parse confluence JSON on attempt {attempt+1}. Retrying...")
            continue
            
    if parsed_json is None:
        parsed_json = {
            "error": "Failed to parse JSON output after retries.",
            "raw_output": raw_analysis
        }
        
    print(f"[{ticker}] Confluence analysis complete.")
    
    # Run mathematical clustering for Support/Resistance
    from src.quant_calculations import cluster_support_resistance
    
    current_price = 0.0
    scraped = state.get("scraped_data", {})
    if isinstance(scraped, dict):
        history = scraped.get("history", scraped.get("historical_data", scraped.get("data", [])))
        if history and len(history) > 0:
            current_price = float(history[-1].get("Close", history[-1].get("close", 0.0)))
    elif isinstance(scraped, list) and len(scraped) > 0:
        current_price = float(scraped[-1].get("Close", scraped[-1].get("close", 0.0)))
        
    clustered_sr = cluster_support_resistance(vision_features, technical_indicators, current_price, tolerance_pct=0.015)
    parsed_json["clustered_sr"] = clustered_sr
    
    # Return confluence_analysis, and keep validation_result populated to preserve backward compatibility for Decision node
    return {
        "confluence_analysis": parsed_json,
        "validation_result": json.dumps(parsed_json, indent=2)
    }

from src.risk_calculations import calculate_risk_parameters

def node_risk_management(state: TradingState) -> dict:
    ticker = state["ticker"]
    tech_ind = state.get("technical_indicators", {})
    confluence = state.get("confluence_analysis", {})
    scraped = state.get("scraped_data", {})
    
    print(f"[{ticker}] Running risk management calculations...")
    
    risk_params = calculate_risk_parameters(tech_ind, confluence, scraped)
    
    print(f"[{ticker}] Risk management complete.")
    return {"risk_analysis": risk_params}

def node_decision_engine(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_features = state.get("vision_features", {})
    technical_indicators = state.get("technical_indicators", {})
    confluence_analysis = state.get("confluence_analysis", {})
    unified_trend = state.get("unified_trend", {})
    risk_analysis = state.get("risk_analysis", {})
    
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": technical_indicators.get("interpretations", {}),
        "pivot_points": technical_indicators.get("pivot_points", {})
    }
    
    print(f"[{ticker}] Running decision engine...")
    
    prompt = f"""
    You are an expert institutional technical analyst for {ticker}.
    Your responsibility is to review the following analyses and provide a highly structured, objective evaluation.
    
    Unified Trend Engine Output:
    {json.dumps(unified_trend)}
    
    Available Visual Features:
    {json.dumps(vision_features)}
    
    Available Technical Indicators (Quantitative):
    {json.dumps(simplified_quantitative)}
    
    Confluence Analysis:
    {json.dumps(confluence_analysis)}
    
    Risk Management Profile:
    {json.dumps(risk_analysis)}
    
    INSTRUCTIONS (CRITICAL):
    1. You must evaluate 10 distinct technical components. Base trend on Unified Trend Output. Base indicator impact strictly on provided interpretations.
    2. STRICT STATE SYNCHRONIZATION: If an indicator's impact is "Bearish" or "Bearish Reinforcement" (e.g., ADX), its mathematical score MUST be negative. You are strictly prohibited from listing a Bearish or Bearish Reinforcement metric in the top_3_bullish_factors.
    3. For each component, assign a mathematical score between -1.0 (Maximally Bearish) and 1.0 (Maximally Bullish). If a component is completely unavailable, undetected, or not applicable, return the exact string "N/A" for the score.
    4. Provide a brief 1-sentence reason for each score.
    5. Provide the top 3 bullish factors and top 3 bearish factors overall.
    6. GOLDEN RULE: The report should never read like independent AI modules stitched together. It should read like one experienced institutional technical analyst who has considered every indicator before writing a single coherent conclusion. Every statement should be derived from a shared internal analysis state. No section should contradict another. If uncertainty exists, explain WHY rather than reporting conflicting facts.
    7. Summarize the institutional narrative for your recommendation, explaining the logic contextually.
    8. Identify key risks that could invalidate the trade.
    
    COMPONENTS TO EVALUATE:
    1. trend_strength
    2. momentum
    3. market_structure
    4. volume_confirmation
    5. support_resistance
    6. risk_reward
    7. multi_timeframe_alignment (Set score to "N/A" if not enough data)
    8. candlestick_patterns
    9. chart_patterns
    10. volatility
    
    RETURN EXACTLY THIS JSON SCHEMA (NO OTHER TEXT):
    {{
        "decision": {{
            "component_scores": {{
                "trend_strength": {{"score": 0.0, "reason": "..."}},
                "momentum": {{"score": 0.0, "reason": "..."}},
                "market_structure": {{"score": 0.0, "reason": "..."}},
                "volume_confirmation": {{"score": 0.0, "reason": "..."}},
                "support_resistance": {{"score": 0.0, "reason": "..."}},
                "risk_reward": {{"score": 0.0, "reason": "..."}},
                "multi_timeframe_alignment": {{"score": "N/A", "reason": "..."}},
                "candlestick_patterns": {{"score": "N/A", "reason": "..."}},
                "chart_patterns": {{"score": "N/A", "reason": "..."}},
                "volatility": {{"score": 0.0, "reason": "..."}}
            }},
            "top_3_bullish_factors": ["...", "...", "..."],
            "top_3_bearish_factors": ["...", "...", "..."],
            "institutional_narrative": "...",
            "key_risks": ["...", "..."],
            "execution": {{
                "entry": 0,
                "stop_loss": 0,
                "targets": {{
                    "target_1": 0,
                    "target_2": 0,
                    "target_3": 0
                }}
            }}
        }}
    }}
    
    NOTE: For the "execution" block, strictly copy the values from the provided Risk Management Profile JSON. Do NOT calculate them yourself.
    """
    
    parsed_json = None
    raw_analysis = ""
    
    for attempt in range(2):
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt
            }],
            options={'temperature': 0.0}
        )
        raw_analysis = response['message']['content']
        
        # Robust parsing
        cleaned_str = raw_analysis.strip()
        if cleaned_str.startswith("```json"):
            cleaned_str = cleaned_str[7:]
        elif cleaned_str.startswith("```"):
            cleaned_str = cleaned_str[3:]
            
        if cleaned_str.endswith("```"):
            cleaned_str = cleaned_str[:-3]
            
        cleaned_str = cleaned_str.strip()
        
        try:
            parsed_json = json.loads(cleaned_str)
            
            if parsed_json and "decision" in parsed_json:
                decision = parsed_json["decision"]
                
                # Retrieve individual scores
                c_scores = decision.get("component_scores", {})
                
                # Define institutional weights
                weights = {
                    "trend_strength": 0.15,
                    "momentum": 0.15,
                    "market_structure": 0.15,
                    "volume_confirmation": 0.10,
                    "support_resistance": 0.10,
                    "risk_reward": 0.10,
                    "multi_timeframe_alignment": 0.10,
                    "candlestick_patterns": 0.05,
                    "chart_patterns": 0.05,
                    "volatility": 0.05
                }
                
                # Deterministic Risk/Reward Override
                best_rr = risk_analysis.get("metrics", {}).get("best_risk_reward", 0.0)
                try:
                    rr_val = float(best_rr)
                    if rr_val < 1:
                        rr_score = -1.0
                    elif rr_val < 1.5:
                        rr_score = -0.5
                    elif rr_val < 2:
                        rr_score = 0.0
                    elif rr_val < 3:
                        rr_score = 0.5
                    else:
                        rr_score = 1.0
                        
                    if "risk_reward" not in c_scores:
                        c_scores["risk_reward"] = {}
                    c_scores["risk_reward"]["score"] = rr_score
                    c_scores["risk_reward"]["reason"] = f"Deterministic RR Score based on {rr_val} R:R."
                except (ValueError, TypeError):
                    pass

                invalid_keywords = ["unknown", "none", "not detected", "no pattern", "unavailable", "insufficient", "absent", "not found", "no clear"]
                
                active_weights = {}
                for comp, weight in weights.items():
                    val = c_scores.get(comp, {}).get("score", "N/A")
                    reason = str(c_scores.get(comp, {}).get("reason", "")).lower()
                    
                    is_invalid = val == "N/A" or any(kw in reason for kw in invalid_keywords)
                    if not is_invalid:
                        active_weights[comp] = weight

                total_active_weight = sum(active_weights.values())
                if total_active_weight <= 0.0:
                    total_active_weight = 1.0
                    
                net_evidence = 0.0
                score_breakdown = []
                
                for comp, original_weight in weights.items():
                    val = c_scores.get(comp, {}).get("score", "N/A")
                    reason = str(c_scores.get(comp, {}).get("reason", "")).lower()
                    
                    is_invalid = val == "N/A" or any(kw in reason for kw in invalid_keywords)
                    
                    if is_invalid:
                        score_breakdown.append({
                            "component": comp.replace("_", " ").title(),
                            "weight": "0% (Excluded)",
                            "normalized_score": 0.0,
                            "contribution": "+0.0"
                        })
                        continue
                        
                    try:
                        val_float = float(val)
                    except (ValueError, TypeError):
                        val_float = 0.0
                        
                    # Trend Math Gating for ADX
                    if comp == "trend_strength":
                        adx_interp = technical_indicators.get("interpretations", {}).get("ADX", {}).get("Impact", "")
                        if adx_interp == "Bearish Reinforcement" and val_float > 0:
                            val_float = -val_float # Flip to negative if ADX reinforces bearishness
                            if "score" in c_scores.get(comp, {}):
                                c_scores[comp]["reason"] += " (System flipped to negative due to Bearish ADX)."
                    
                    # Clamp to [-1.0, 1.0] just in case
                    val_float = max(-1.0, min(1.0, val_float))
                    
                    # Normalize weight
                    normalized_weight = original_weight / total_active_weight
                    weighted_val = val_float * normalized_weight
                    net_evidence += weighted_val
                    
                    score_breakdown.append({
                        "component": comp.replace("_", " ").title(),
                        "weight": f"{int(normalized_weight * 100)}%",
                        "normalized_score": round(val_float, 2),
                        "contribution": f"{round(weighted_val * 100, 2):+}"
                    })
                    
                # net_evidence ranges from -1.0 to 1.0. Scale to 0-100.
                overall_score = (net_evidence + 1.0) / 2.0 * 100.0
                
                # Confidence Calculation directly from score
                confidence = overall_score / 100.0
                    
                # Map Overall Score to Recommendation
                if overall_score >= 85:
                    rec = "STRONG BUY"
                elif overall_score >= 65:
                    rec = "BUY"
                elif overall_score >= 40:
                    rec = "HOLD"
                elif overall_score >= 20:
                    rec = "SELL"
                else:
                    rec = "AVOID"
                    
                # Map Overall Score to Strength
                if overall_score >= 85:
                    strength = "Very Strong"
                elif overall_score >= 65:
                    strength = "Strong"
                elif overall_score >= 45:
                    strength = "Moderate"
                elif overall_score >= 25:
                    strength = "Weak"
                else:
                    strength = "Very Weak"
                    
                decision["overall_score"] = round(overall_score, 1)
                decision["recommendation"] = rec
                decision["confidence"] = round(confidence, 2)
                decision["strength"] = strength
                decision["score_breakdown"] = score_breakdown
                    
            break
        except json.JSONDecodeError:
            print(f"[{ticker}] Warning: Failed to parse decision JSON on attempt {attempt+1}. Retrying...")
            continue
            
    if parsed_json is None:
        parsed_json = {
            "error": "Failed to parse JSON output after retries.",
            "raw_output": raw_analysis
        }
        
    print(f"[{ticker}] Decision engine complete.")
    
    return {
        "decision": parsed_json,
        "final_decision": json.dumps(parsed_json, indent=2) # Backward compatibility
    }

from src.trade_validation import validate_trade_parameters

def node_trade_validator(state: TradingState) -> dict:
    ticker = state["ticker"]
    tech_ind = state.get("technical_indicators", {})
    confluence = state.get("confluence_analysis", {})
    risk = state.get("risk_analysis", {})
    decision = state.get("decision", {})
    
    unified_trend = state.get("unified_trend", {})
    
    print(f"[{ticker}] Running trade validator...")
    
    validation_results = validate_trade_parameters(tech_ind, confluence, risk, decision, unified_trend)
    
    if not validation_results["valid"]:
        print(f"[{ticker}] WARNING: Trade validation failed with {len(validation_results['errors'])} errors.")
        for err in validation_results['errors']:
            print(f"  - {err}")
            
    if validation_results["warnings"]:
        for warn in validation_results["warnings"]:
            if isinstance(warn, dict):
                print(f"[{ticker}] Validation Warning: {warn.get('reason', warn)}")
            else:
                print(f"[{ticker}] Validation Warning: {warn}")
    
    print(f"[{ticker}] Trade validation complete.")
    
    return {"trade_validation": validation_results, "decision": decision}

def build_report_prompt(ticker, vision_features, technical_indicators, confluence_analysis, risk_analysis, decision, trade_validation) -> str:
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": technical_indicators.get("interpretations", {}),
        "pivot_points": technical_indicators.get("pivot_points", {})
    }

    return f"""
    You are the final Report Generator for VisuQuant for {ticker}.
    Your responsibility is to transform the structured outputs from previous nodes into a professional, institutional-quality report.
    
    CRITICAL STRICT RULES:
    - You MUST NEVER modify Recommendation, Confidence, Entry, Stop Loss, Targets, Position Size, Risk Level, Confluence, Technical Indicators, Vision Analysis, or Validation Results.
    - NEVER generate new indicators, calculations, or recommendations.
    - ONLY use the supplied JSON. Do not infer missing values. Do not invent missing information.
    - NEVER expose internal JSON structures, raw machine objects, or booleans in the final text.
    - Provide exact numerical values where available.
    - CRITICAL: For EMA, RSI, and MACD, you MUST exactly copy the text from the `interpretations` object inside Technical Indicators. Do NOT invent your own interpretation of the raw numbers.
    - If unavailable, generate exactly: "Unavailable. Reason: Insufficient historical candles."
    - If data is unavailable, explicitly state that it is unavailable using the rule above.
    - Do NOT simply list every quantitative value. Explain what the indicators collectively suggest.
    - Style: Professional, Institutional, Evidence-based, Objective, Concise, Readable. No emojis, no sensational language, no speculation, no repetition.
    
    SUPPLIED DATA:
    Vision Features: {json.dumps(vision_features)}
    Technical Indicators: {json.dumps(simplified_quantitative)}
    Confluence Analysis: {json.dumps(confluence_analysis)}
    Risk Analysis: {json.dumps(risk_analysis)}
    Decision Engine: {json.dumps(decision)}
    Trade Validation: {json.dumps(trade_validation)}
    
    RETURN YOUR REPORT AS PURE MARKDOWN. Do NOT wrap it in JSON.
    Use the following 9 sections as headers:
    1. Executive Summary: Include Stock Symbol, Current Market Trend, Final Recommendation, Decision Confidence, Overall Confluence, and Trade Validation Status.
    2. Vision Analysis: Summarize ONLY the `Vision Features` JSON. Present the data as a clean Markdown Table (e.g. | Metric | Observation |).
    3. Quantitative Analysis: Summarize ONLY the `Technical Indicators` JSON. Present the data as a clean Markdown Table. You MUST read the `interpretations` (EMA alignment, RSI condition, MACD condition). Explain what they collectively suggest. Do NOT mention visual features here.
    4. Confluence Analysis: Present areas of agreement/contradiction and missing data in a clean Markdown Table. Explain WHY the confluence score reached its value.
    5. Risk Analysis: Present Entry, Stop Loss, Target 1, Target 2, Target 3, Risk/Reward, Position Size, Volatility, Risk Level, Warnings exactly as received in a clean Markdown Table.
    6. Decision Summary: Present Recommendation, Confidence, Supporting Factors, Risk Factors in a clean Markdown Table. Copy Execution Plan directly from Decision Engine.
    7. Validation Summary: If passed: state it passed all deterministic validation checks. If failed: explain Errors, Warnings, Failed Checks.
    8. Overall Conclusion: Provide closing summary discussing market condition, overall trade quality, primary strengths/risks, and final recommendation.
    
    TABLE FORMATTING CRITICAL RULE:
    For EVERY section (2 to 6), you MUST use Markdown tables. Do NOT use bullet points for data listing. Ensure headers are bold and properly aligned.
    9. Disclaimer: "This report is generated using AI-assisted technical analysis together with deterministic quantitative models. It is intended for research and educational purposes only and should not be interpreted as financial advice."
    """

def node_report_generator(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision = state.get("vision_features", {})
    tech = state.get("technical_indicators", {})
    confluence = state.get("confluence_analysis", {})
    risk = state.get("risk_analysis", {})
    decision = state.get("decision", {})
    validation = state.get("trade_validation", {})
    
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": tech.get("interpretations", {}),
        "pivot_points": tech.get("pivot_points", {})
    }
    
    print(f"[{ticker}] Generating final institutional report...")
    
    prompt = f"""
    You are an expert institutional quantitative analyst. 
    Write a final summary report for {ticker}.
    
    Inputs (STRICTLY USE THESE):
    Vision: {json.dumps(vision)}
    Technical: {json.dumps(simplified_quantitative)}
    Confluence: {json.dumps(confluence)}
    Risk: {json.dumps(risk)}
    Decision: {json.dumps(decision)}
    Validation: {json.dumps(validation)}
    
    NARRATIVE RULE (CRITICAL):
    Do NOT simply list facts or output raw JSON values. Generate professional, analyst-style explanations that synthesize the data.
    GOLDEN RULE: The report should never read like independent AI modules stitched together. It should read like one experienced institutional technical analyst who has considered every indicator before writing a single coherent conclusion.
    Every statement should be derived from a shared internal analysis state. No section should contradict another. If uncertainty exists, explain WHY rather than reporting conflicting facts.
    
    For example:
    BAD: "Trend = Bullish. Momentum = Bearish."
    GOOD: "The primary trend remains bullish as confirmed by EMA alignment and an ascending trendline. However, momentum indicators such as RSI and MACD suggest weakening buying pressure, indicating a higher probability of short-term consolidation rather than trend reversal."
    
    Generate similar professional commentary for: Trend, Momentum, Volume, Support, Resistance, Risk, and the Final Recommendation.
    
    RETURN YOUR REPORT AS PURE MARKDOWN.
    Use these 9 sections:
    1. Executive Summary, 2. Vision Analysis, 3. Quantitative Analysis, 4. Confluence Analysis, 5. Risk Analysis, 6. Decision Summary, 7. Validation Summary, 8. Overall Conclusion, 9. Disclaimer.
    """
    
    raw_analysis = ""
    
    for attempt in range(2):
        try:
            response = ollama.chat(
                model='qwen2.5vl:7b',
                messages=[{
                    'role': 'user',
                    'content': prompt
                }],
                options={'temperature': 0.0}
            )
            raw_analysis = response['message']['content']
            break
        except Exception as e:
            print(f"[{ticker}] Warning: Failed to generate report on attempt {attempt+1}. Retrying...")
            continue
            
    if not raw_analysis:
        print(f"[{ticker}] ERROR: Failed to generate report. Returning fallback.")
        raw_analysis = "Report generation failed due to an LLM error."
        
    print(f"[{ticker}] Report generation complete.")
    
    return {
        "analysis_report": {"status": "Generated as Markdown"},
        "analysis_report_markdown": raw_analysis,
        "final_report": raw_analysis
    }
