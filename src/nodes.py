import os
import json
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

def node_validation_engine(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_analysis = state.get("vision_analysis", "")
    scraped_data = state.get("scraped_data", {})
    
    print(f"[{ticker}] Running validation engine (cross-checking data)...")
    
    prompt = f"""
    You are an expert trading AI validator. Cross-verify the visual price action analysis with the scraped quantitative data for {ticker}.
    
    Vision Analysis (from chart):
    {vision_analysis}
    
    Scraped Quantitative Data:
    {scraped_data}
    
    Highlight any confluences or contradictions between the visual chart patterns and the quantitative data.
    Output a structured validation result.
    """
    
    response = ollama.chat(
        model='qwen2.5vl:7b',
        messages=[{
            'role': 'user',
            'content': prompt
        }]
    )
    validation_result = response['message']['content']
        
    print(f"[{ticker}] Validation complete.")
    return {"validation_result": validation_result}

def node_decision_agent(state: TradingState) -> dict:
    ticker = state["ticker"]
    validation_result = state.get("validation_result", "")
    
    print(f"[{ticker}] Running decision and risk agent...")
    
    prompt = f"""
    You are an expert trading AI Decision & Risk Agent. Based on the following validated data for {ticker}:
    
    {validation_result}
    
    Formulate a final trading decision (e.g., STRONG BUY, BUY, HOLD, SELL, STRONG SELL).
    Include risk metrics and a short, decisive rationale.
    """
    
    response = ollama.chat(
        model='qwen2.5vl:7b',
        messages=[{
            'role': 'user',
            'content': prompt
        }]
    )
    decision = response['message']['content']
        
    print(f"[{ticker}] Final decision generated.")
    return {"final_decision": decision}
