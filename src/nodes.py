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
    If you detect contradictions in your own visual assessment (e.g. you see a Downtrend but the structure is Higher Highs), you MUST set "consistency_status" to "FAILED", populate the "warnings" array explaining the visual contradiction, and drastically reduce your confidence score.

    Extract:
    1. Trend (Direction and Visual confidence 0-100)
    2. Price Structure (Higher Highs, Higher Lows, Lower Highs, Lower Lows)
    3. Support Zones (Approximate price, Strength)
    4. Resistance Zones (Approximate price, Strength)
    5. Chart Patterns & Candlestick Patterns
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
    
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": technical_indicators.get("interpretations", {}),
        "pivot_points": technical_indicators.get("pivot_points", {})
    }
    
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
    - Trend (Vision vs Quantitative `ema_trend`)
    - Momentum (Quantitative `rsi_condition` and `macd_condition`)
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
    
    # Strip raw numerical noise to prevent LLM hallucinations
    simplified_quantitative = {
        "interpretations": technical_indicators.get("interpretations", {}),
        "pivot_points": technical_indicators.get("pivot_points", {})
    }
    
    print(f"[{ticker}] Running decision engine...")
    
    min_risk_reward = 1.5
    
    prompt = f"""
    You are the final institutional trading decision engine for {ticker}.
    Your responsibility is to review completed analyses.
    
    Available Visual Features:
    {json.dumps(vision_features)}
    
    Available Technical Indicators (Quantitative):
    {json.dumps(simplified_quantitative)}
    
    Confluence Analysis:
    {json.dumps(confluence_analysis)}
    
    Risk Management Profile:
    {json.dumps(risk_analysis)}
    
    Do not perform calculations.
    Do not generate numerical estimates.
    Do not invent missing information.
    Base every conclusion only on the supplied structured JSON.
    If evidence is contradictory, prefer HOLD over speculative recommendations.
    Confidence must reflect the quality and consistency of the supplied evidence.
    
    If confluence is weak OR risk is high, become more conservative.
    If evidence is contradictory, prefer HOLD over speculative recommendations.
    If you recommend HOLD due to contradictory evidence, your "why_chosen" MUST explicitly state: "HOLD recommended due to contradictory evidence between vision and quantitative metrics", NOT because of risk/reward.
    
    REASONING ARRAY RULE (CRITICAL):
    For your "reasoning" array, you MUST directly copy the category, status, and reasons from the supplied Confluence Analysis.
    Do NOT re-evaluate the trend yourself. Do NOT hallucinate mathematical comparisons (like EMA20 > SMA20) if they contradict the Confluence Engine.
    
    RISK REWARD THRESHOLD (CRITICAL):
    You MUST read the "metrics" -> "meets_min_rr_threshold" boolean value from the Risk Management Profile.
    If "meets_min_rr_threshold" is false, you MUST NEVER recommend BUY, SELL, STRONG BUY, or STRONG SELL.
    Instead, you MUST recommend "HOLD" and your "why_chosen" field MUST explicitly state: "Risk Reward below acceptable threshold."
    
    HOLD RULE (CRITICAL):
    If your recommendation is "HOLD", you MUST NOT provide trading execution parameters.
    For a HOLD recommendation, your execution block MUST exactly match this:
    "execution": {{
        "status": "Inactive",
        "entry": null,
        "stop_loss": null,
        "targets": [],
        "reason": "No actionable trade."
    }}
    
    CONFIDENCE MAPPING RULE:
    Your recommendation MUST align with the Confluence Analysis `overall_score`:
    - 0.85 - 1.00: STRONG BUY or STRONG SELL
    - 0.70 - 0.85: BUY or SELL
    - 0.50 - 0.70: HOLD
    - 0.00 - 0.40: AVOID (Output as HOLD)
    Confidence decreases because of contradictions, it does NOT collapse to 0 just because the recommendation is HOLD.

    RETURN EXACTLY THIS JSON SCHEMA:
    {{
        "decision": {{
            "recommendation": "STRONG BUY | BUY | HOLD | SELL | STRONG SELL",
            "confidence": 0,
            "strength": "High | Medium | Low",
            "why_chosen": "...",
            "alternatives_rejected": "...",
            "reasoning": [
                {{
                    "category": "Trend | Momentum | Support Resistance | Volume | Patterns | Risk",
                    "weight": 0,
                    "status": "Confirmed | Contradiction | Partially Confirmed | Unavailable",
                    "evidence": [
                        "..."
                    ],
                    "reason": "..."
                }}
            ],
            "supporting_factors": [
                "..."
            ],
            "risk_factors": [
                "..."
            ],
            "execution": {{
                "status": "Active | Inactive",
                "entry": 0,
                "stop_loss": 0,
                "targets": {{
                    "target_1": 0,
                    "target_2": 0,
                    "target_3": 0
                }},
                "position_size": "...",
                "reason": "..."
            }}
        }}
    }}
    
    NOTE: For the "execution" block (if not HOLD), strictly copy the values from the provided Risk Management Profile JSON. Do NOT calculate them yourself.
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
            
            # Strictly enforce HOLD logic and Mathematical Confidence in post-processing
            if parsed_json and "decision" in parsed_json:
                decision = parsed_json["decision"]
                
                # Enforce Mathematical Confidence based on Confluence Score
                conf_score = 0
                if confluence_analysis:
                    conf_obj = confluence_analysis.get("confluence_analysis", confluence_analysis)
                    conf_score = float(conf_obj.get("overall_score", 0))
                decision["confidence"] = conf_score
                
                # Determine recommendation strength based on user mapping if not driven by Risk/Reward
                # The LLM chooses the direction (BUY/SELL) and RR logic, we ensure confidence doesn't drop to 0
                
                if decision.get("recommendation") == "HOLD":
                    decision["execution"] = {
                        "status": "Inactive",
                        "entry": None,
                        "stop_loss": None,
                        "targets": [],
                        "reason": "No actionable trade."
                    }
                    
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
