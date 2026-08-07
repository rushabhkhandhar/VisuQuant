import os
import json
import traceback
from datetime import datetime

def create_output_directory(ticker: str) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    folder_name = f"{timestamp}_{ticker}"
    
    # Project root is two levels up from src/reporting
    root_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
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
        
        md_content = final_state.get("final_report")
        if not md_content:
            md_content = final_state.get("analysis_report_markdown", "Report generation skipped or failed.")
            
        # Generate Premium PDF Dashboard via xhtml2pdf
        import jinja2
        from xhtml2pdf import pisa
        
        # Load the Jinja2 template
        template_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
        env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir))
        template = env.get_template("report.html")
        
        # Render HTML string with JSON data
        html_content = template.render(
            ticker=ticker,
            date=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            decision=final_state.get("decision", {}),
            risk=final_state.get("risk_analysis", {}),
            confluence=final_state.get("confluence_analysis", {}),
            tech=final_state.get("technical_indicators", {}),
            vision=final_state.get("vision_features", {}),
            validation=final_state.get("trade_validation", {}),
            announcements=final_state.get("announcements", [])
        )
        
        pdf_path = os.path.join(output_dir, f"{ticker}_analysis_report.pdf")
        with open(pdf_path, "wb") as pdf_file:
            pisa.CreatePDF(html_content, dest=pdf_file)
            
        # JSON dumping disabled to save disk space
        # if "vision_features" in final_state: save_json(os.path.join(output_dir, "vision_features.json"), final_state["vision_features"])
        # if "technical_indicators" in final_state: save_json(os.path.join(output_dir, "technical_indicators.json"), final_state["technical_indicators"])
        # if "confluence_analysis" in final_state: save_json(os.path.join(output_dir, "confluence_analysis.json"), final_state["confluence_analysis"])
        # if "risk_analysis" in final_state: save_json(os.path.join(output_dir, "risk_analysis.json"), final_state["risk_analysis"])
        # if "decision" in final_state: save_json(os.path.join(output_dir, "decision.json"), final_state["decision"])
        # if "trade_validation" in final_state: save_json(os.path.join(output_dir, "trade_validation.json"), final_state["trade_validation"])
        # save_pipeline_state(output_dir, final_state)
        save_metadata(output_dir, ticker, start_time, end_time)
        
        # Output confirmation
        print("\n" + "="*50)
        print(f"Premium Dashboard PDF successfully generated!")
        print(f"Saved to: {pdf_path}")
        print("="*50)
        
        return pdf_path
        
    except Exception as e:
        print("\nFailed to persist pipeline results!")
        traceback.print_exc()
        return None
