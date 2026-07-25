import os
import json
import traceback
from datetime import datetime

def create_output_directory(ticker: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder_name = f"{timestamp}_{ticker}"
    
    # Project root is one level up from src
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    output_dir = os.path.join(root_dir, "outputs", folder_name)
    
    os.makedirs(output_dir, exist_ok=True)
    return output_dir

def save_json(filepath: str, data: dict):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
    except Exception as e:
        print(f"Error saving JSON to {filepath}: {e}")

def save_markdown(filepath: str, content: str):
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
    except Exception as e:
        print(f"Error saving markdown to {filepath}: {e}")

def save_pipeline_state(output_dir: str, state: dict):
    filepath = os.path.join(output_dir, "pipeline_state.json")
    save_json(filepath, state)

def save_metadata(output_dir: str, ticker: str, start_time: float, end_time: float):
    duration = round(end_time - start_time, 2)
    timestamp = datetime.fromtimestamp(start_time).strftime("%Y-%m-%dT%H:%M:%S")
    
    metadata = {
        "ticker": ticker,
        "execution_time": timestamp,
        "pipeline_version": "1.0",
        "llm_provider": "Ollama",
        "model": "Qwen2.5-VL",
        "status": "SUCCESS",
        "execution_duration_seconds": duration
    }
    filepath = os.path.join(output_dir, "metadata.json")
    save_json(filepath, metadata)

def persist_pipeline_results(final_state: dict, start_time: float, end_time: float):
    ticker = final_state.get("ticker", "UNKNOWN")
    try:
        output_dir = create_output_directory(ticker)
        
        # 1. Save metadata
        save_metadata(output_dir, ticker, start_time, end_time)
        
        # 2. Save pipeline state
        save_pipeline_state(output_dir, final_state)
        
        # 3. Save individual JSON components (handle SKIPPED)
        components = [
            ("vision_features", "vision_features.json"),
            ("technical_indicators", "technical_indicators.json"),
            ("confluence_analysis", "confluence_analysis.json"),
            ("risk_analysis", "risk_analysis.json"),
            ("decision", "decision.json"),
            ("trade_validation", "trade_validation.json"),
            ("analysis_report", "analysis_report.json")
        ]
        
        for key, filename in components:
            filepath = os.path.join(output_dir, filename)
            data = final_state.get(key)
            if data is None:
                data = {
                    "status": "SKIPPED",
                    "reason": f"{key} analysis unavailable or skipped."
                }
            save_json(filepath, data)
            
        # 4. Save markdown report
        md_content = final_state.get("final_report")
        if not md_content:
            md_content = final_state.get("analysis_report_markdown", "Report generation skipped or failed.")
            
        save_markdown(os.path.join(output_dir, "analysis_report.md"), md_content)
        
        # 5. Output confirmation
        print("\n" + "="*50)
        print(f"Results saved to\noutputs/{os.path.basename(output_dir)}/")
        print("="*50)
        
    except Exception as e:
        print("\nFailed to persist pipeline results!")
        traceback.print_exc()
