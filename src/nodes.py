import os
import json
import pandas as pd
import ollama
from playwright.sync_api import sync_playwright

from src.state import TradingState
from src.scraper import fetch_nse_data

def node_capture_chart(state: TradingState) -> dict:
    ticker = state["ticker"]
    print(f"[{ticker}] Capturing TradingView chart...")
    
    chart_path = f"{ticker}_chart.png"
    
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
            page.screenshot(path=chart_path)
            print(f"[{ticker}] Chart captured and saved to {chart_path}")
        except Exception as e:
            print(f"[{ticker}] Failed to capture chart: {e}")
            chart_path = None
        finally:
            browser.close()
        
    return {"chart_image_path": chart_path}

def node_run_nse_scraper(state: TradingState) -> dict:
    ticker = state["ticker"]
    data = fetch_nse_data(ticker)
    return {"scraped_data": data}

def node_vision_analysis(state: TradingState) -> dict:
    ticker = state["ticker"]
    chart_path = state.get("chart_image_path")
    print(f"[{ticker}] Running vision feature extraction on {chart_path}...")
    
    if not chart_path or not os.path.exists(chart_path):
        err = {"error": "Chart image not found or not captured."}
        return {"vision_features": err, "vision_analysis": json.dumps(err)}

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
                'images': [chart_path]
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
