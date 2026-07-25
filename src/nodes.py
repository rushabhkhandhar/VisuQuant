import os
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
    print(f"[{ticker}] Running vision analysis on {chart_path}...")
    
    if not chart_path or not os.path.exists(chart_path):
        return {"vision_analysis": "Error: Chart image not found or not captured."}

    prompt = (
        f"Analyze the technical chart for {ticker}. "
        "Identify key chart patterns, support and resistance levels, and the overall trend. "
        "Provide a concise technical summary."
    )
    
    try:
        response = ollama.chat(
            model='qwen2.5-vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt,
                'images': [chart_path]
            }]
        )
        analysis = response['message']['content']
    except Exception as e:
        analysis = f"Error during vision analysis: {e}"
        
    print(f"[{ticker}] Vision analysis complete.")
    return {"vision_analysis": analysis}

def node_validation_and_decision(state: TradingState) -> dict:
    ticker = state["ticker"]
    vision_analysis = state.get("vision_analysis", "")
    scraped_data = state.get("scraped_data", {})
    
    print(f"[{ticker}] Running final validation and decision...")
    
    prompt = f"""
    You are an expert trading AI. Cross-verify the visual price action analysis with the scraped quantitative data for {ticker}.
    
    Vision Analysis (from chart):
    {vision_analysis}
    
    Scraped Quantitative Data:
    {scraped_data}
    
    Based on this combined information, formulate a final trading decision (e.g., STRONG BUY, BUY, HOLD, SELL, STRONG SELL) and a short rationale.
    """
    
    try:
        # Using qwen2.5-vl:7b for consistency, although a non-vision model could also work here
        response = ollama.chat(
            model='qwen2.5-vl:7b',
            messages=[{
                'role': 'user',
                'content': prompt
            }]
        )
        decision = response['message']['content']
    except Exception as e:
        decision = f"Error during decision making: {e}"
        
    print(f"[{ticker}] Final decision generated.")
    return {"final_decision": decision}
