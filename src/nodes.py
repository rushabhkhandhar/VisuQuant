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
        # Navigate to TradingView for the given ticker
        url = f"https://in.tradingview.com/chart/?symbol=NSE%3A{ticker}"
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            # Wait a few seconds for the actual canvas to render fully
            page.wait_for_timeout(5000)
            screenshot_bytes = page.screenshot()
            b64_image = base64.b64encode(screenshot_bytes).decode('utf-8')
            print(f"[{ticker}] Chart captured successfully as base64 string.")
        except Exception as e:
            print(f"[{ticker}] Failed to capture chart: {e}")
        finally:
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

    - Return VALID JSON only.
    - No markdown.
    - No explanations.
    - No BUY/SELL/HOLD recommendation.
    - Do not estimate indicators that are not visibly plotted.
    - If something is not visible, return null.
    - Never invent values.

    Extract:

    1. Trend
    - Direction
    - Visual confidence (0-100)

    2. Price Structure
    - Higher Highs
    - Higher Lows
    - Lower Highs
    - Lower Lows

    3. Support Zones
    - Approximate price
    - Strength

    4. Resistance Zones
    - Approximate price
    - Strength

    5. Chart Patterns

    6. Candlestick Patterns

    7. Trendlines
    - Type
    - Number of touches
    - Broken or not

    8. Channels

    9. Visible Indicators
    - EMA20
    - EMA50
    - EMA200
    - VWAP
    - Bollinger Bands
    - RSI
    - MACD
    - Volume

    10. Events
    - Breakout
    - Breakdown
    - Retest
    - Gap Up
    - Gap Down

    11. Volume
    - Increasing
    - Decreasing
    - Spike

    If any field cannot be determined from the image,
    return null instead of guessing.

    RETURN EXACTLY THIS JSON SCHEMA:
    {{
      "trend": {{
        "direction": "Uptrend | Downtrend | Sideways | Unknown",
        "confidence": 0
      }},
      "price_structure": {{
        "higher_highs": true,
        "higher_lows": true,
        "lower_highs": false,
        "lower_lows": false
      }},
      "support_zones": [
        {{
          "approx_price": 0,
          "strength": "Strong | Medium | Weak"
        }}
      ],
      "resistance_zones": [
        {{
          "approx_price": 0,
          "strength": "Strong | Medium | Weak"
        }}
      ],
      "patterns": {{
        "chart": [],
        "candlestick": []
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
            }]
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

def node_confluence_engine(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_features = state.get("vision_features", {})
    technical_indicators = state.get("technical_indicators", {})
    
    print(f"[{ticker}] Running confluence engine (evidence synthesis)...")
    
    prompt = f"""
    You are a Confluence Engine for {ticker}. 
    Your task is to compare evidence from visual chart analysis with quantitative market data.

    Your task is ONLY to identify agreements, contradictions, and missing evidence.

    Rules:
    - Return VALID JSON only.
    - No markdown.
    - No explanations outside JSON.
    - No BUY/SELL/HOLD recommendation.
    - No stop-loss or target prices.
    - Do not calculate indicators.
    - Do not estimate missing values.
    - If a field does not exist inside technical indicators or vision features, explicitly list it inside the missing_data field.
    - Never invent values or hallucinate missing information.

    Available Vision Features (from chart):
    {json.dumps(vision_features)}
    
    Available Technical Indicators (Quantitative):
    {json.dumps(technical_indicators)}

    Compare the following whenever available:
    - Trend (Vision vs EMA/SMA/ADX)
    - Momentum (RSI/MACD/Momentum)
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
            "reason": "..."
        }},
        "momentum": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown | Bullish | Bearish",
            "confidence": 0,
            "reason": "..."
        }},
        "volume": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "reason": "..."
        }},
        "support_resistance": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "reason": "..."
        }},
        "patterns": {{
            "status": "Confirmed | Contradiction | Partially Confirmed | Unknown",
            "confidence": 0,
            "reason": "..."
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
            }]
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
    risk_analysis = state.get("risk_analysis", {})
    
    print(f"[{ticker}] Running decision engine...")
    
    prompt = f"""
    You are the final institutional trading decision engine for {ticker}.
    Your responsibility is to review completed analyses.
    
    Do not perform calculations.
    Do not generate numerical estimates.
    Do not invent missing information.
    Base every conclusion only on the supplied structured JSON.
    If evidence is contradictory, prefer HOLD over speculative recommendations.
    Confidence must reflect the quality and consistency of the supplied evidence.

    Available Vision Features:
    {json.dumps(vision_features)}
    
    Available Technical Indicators:
    {json.dumps(technical_indicators)}
    
    Confluence Analysis:
    {json.dumps(confluence_analysis)}
    
    Risk Management Profile:
    {json.dumps(risk_analysis)}
    
    Decision Philosophy:
    1. Confluence
    2. Risk
    3. Trend
    4. Momentum
    5. Volume
    If confluence is weak OR risk is high, become more conservative.
    If evidence is insufficient, recommend HOLD instead of guessing.

    RETURN EXACTLY THIS JSON SCHEMA:
    {{
        "decision": {{
            "recommendation": "STRONG BUY | BUY | HOLD | SELL | STRONG SELL",
            "confidence": 0,
            "strength": "High | Medium | Low",
            "summary": "...",
            "supporting_factors": [
                "..."
            ],
            "risk_factors": [
                "..."
            ],
            "execution": {{
                "entry": 0,
                "stop_loss": 0,
                "targets": {{
                    "target_1": 0,
                    "target_2": 0,
                    "target_3": 0
                }},
                "position_size": "..."
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
            }]
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
    
    print(f"[{ticker}] Running trade validator...")
    
    validation_results = validate_trade_parameters(tech_ind, confluence, risk, decision)
    
    if not validation_results["valid"]:
        print(f"[{ticker}] WARNING: Trade validation failed with {len(validation_results['errors'])} errors.")
        for err in validation_results['errors']:
            print(f"  - {err}")
            
    if validation_results["warnings"]:
        for warn in validation_results["warnings"]:
            print(f"[{ticker}] Validation Warning: {warn}")
    
    print(f"[{ticker}] Trade validation complete.")
    
    return {"trade_validation": validation_results}

def build_report_prompt(ticker, vision_features, technical_indicators, confluence_analysis, risk_analysis, decision, trade_validation) -> str:
    return f"""
    You are the final Report Generator for VisuQuant for {ticker}.
    Your responsibility is to transform the structured outputs from previous nodes into a professional, institutional-quality report.
    
    CRITICAL STRICT RULES:
    - You MUST NEVER modify Recommendation, Confidence, Entry, Stop Loss, Targets, Position Size, Risk Level, Confluence, Technical Indicators, Vision Analysis, or Validation Results.
    - NEVER generate new indicators, calculations, or recommendations.
    - ONLY use the supplied JSON. Do not infer missing values. Do not invent missing information.
    - If data is unavailable, explicitly state that it is unavailable.
    - Do NOT simply list every quantitative value. Explain what the indicators collectively suggest.
    - Style: Professional, Institutional, Evidence-based, Objective, Concise, Readable. No emojis, no sensational language, no speculation, no repetition.
    
    SUPPLIED DATA:
    Vision Features: {json.dumps(vision_features)}
    Technical Indicators: {json.dumps(technical_indicators)}
    Confluence Analysis: {json.dumps(confluence_analysis)}
    Risk Analysis: {json.dumps(risk_analysis)}
    Decision Engine: {json.dumps(decision)}
    Trade Validation: {json.dumps(trade_validation)}
    
    RETURN EXACTLY THIS JSON SCHEMA:
    {{
        "analysis_report": {{
            "executive_summary": "Include Stock Symbol, Current Market Trend, Final Recommendation, Decision Confidence, Overall Confluence, and Trade Validation Status.",
            "vision_analysis": "Summarize Vision findings (Trend, Market Structure, Support, Resistance, Patterns, etc). Do not invent observations.",
            "quantitative_analysis": "Summarize numerical findings. Highlight observations (EMA alignment, RSI condition, MACD, etc). Explain what they collectively suggest. Do NOT simply list every value.",
            "confluence_analysis": "Explain areas of agreement/contradiction, missing data, and WHY the confluence score reached its value.",
            "risk_analysis": "Present Entry, Stop Loss, Target 1, Target 2, Target 3, Risk/Reward, Position Size, Volatility, Risk Level, Warnings exactly as received.",
            "decision_summary": "Present Recommendation, Confidence, Supporting Factors, Risk Factors. Copy Execution Plan directly from Decision Engine.",
            "validation_summary": "If passed: state it passed all deterministic validation checks. If failed: explain Errors, Warnings, Failed Checks.",
            "overall_conclusion": "Provide closing summary discussing market condition, overall trade quality, primary strengths/risks, and final recommendation.",
            "disclaimer": "This report is generated using AI-assisted technical analysis together with deterministic quantitative models. It is intended for research and educational purposes only and should not be interpreted as financial advice."
        }},
        "analysis_report_markdown": "COMPLETE MARKDOWN FORMATTED REPORT USING THE 9 SECTIONS LISTED ABOVE"
    }}
    """

def node_report_generator(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_features = state.get("vision_features", {})
    technical_indicators = state.get("technical_indicators", {})
    confluence_analysis = state.get("confluence_analysis", {})
    risk_analysis = state.get("risk_analysis", {})
    decision = state.get("decision", {})
    trade_validation = state.get("trade_validation", {})
    
    print(f"[{ticker}] Generating final institutional report...")
    
    prompt = build_report_prompt(ticker, vision_features, technical_indicators, confluence_analysis, risk_analysis, decision, trade_validation)
    
    parsed_json = None
    raw_analysis = ""
    
    for attempt in range(2):
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt
            }]
        )
        raw_analysis = response['message']['content']
        
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
            print(f"[{ticker}] Warning: Failed to parse report JSON on attempt {attempt+1}. Retrying...")
            continue
            
    if parsed_json is None:
        print(f"[{ticker}] ERROR: Failed to generate report JSON.")
        return {}
        
    analysis_report = parsed_json.get("analysis_report", {})
    markdown = parsed_json.get("analysis_report_markdown", "")
    
    print(f"[{ticker}] Report generation complete.")
    
    return {
        "analysis_report": analysis_report,
        "analysis_report_markdown": markdown,
        "final_report": markdown
    }
