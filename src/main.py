import sys
import os
from dotenv import load_dotenv
import warnings

# Load environment variables (e.g. HF_TOKEN)
load_dotenv()
warnings.filterwarnings("ignore")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.workflow.graph import build_graph
from src.reporting.storage import persist_pipeline_results

import subprocess
import time
import urllib.request
import urllib.error

def ensure_ollama_running():
    print("Checking if Ollama is running...")
    try:
        urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
        print("Ollama is already running!") 
        return
    except urllib.error.URLError:
        pass

    print("Starting Ollama server automatically...")
    # Start Ollama in the background
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    
    # Wait for it to become available
    for i in range(15):
        time.sleep(1)
        try:
            urllib.request.urlopen("http://127.0.0.1:11434/", timeout=2)
            print("Ollama server started successfully!")
            return
        except urllib.error.URLError:
            pass
            
    raise RuntimeError("Failed to start Ollama server within 15 seconds. Please ensure it is installed.")

def main():
    import sys
    from datetime import date, datetime
    
    ensure_ollama_running()
    
    payloads = []
    
    print("\n" + "="*50)
    print("Welcome to VisuQuant Orchestrator!")
    print("="*50)
    print("1. Run automated daily screener (Find top candidates)")
    print("2. Analyze a specific ticker")
    
    choice = input("\nEnter your choice (1 or 2): ").strip()
    
    if choice == "1":
        # Run automated screener
        from src.screener.pipeline.handoff import get_handoff_payloads
        
        date_input = input("Enter historical date YYYY-MM-DD (or press Enter for today): ").strip()
        run_date = date.today()
        if date_input:
            try:
                run_date = datetime.strptime(date_input, "%Y-%m-%d").date()
            except ValueError:
                print("Invalid date format. Defaulting to today.")
                
        print(f"\nInitializing automated screening pipeline for {run_date}...")
        payloads = get_handoff_payloads(as_of_date=run_date)
        
        if not payloads:
            print("No actionable signals today. Exiting.")
            return
    else:
        # Single ticker mode
        ticker = input("\nEnter ticker symbol (e.g. RELIANCE): ").strip().upper()
        if not ticker:
            print("Ticker symbol cannot be empty! Exiting.")
            return
            
        print(f"\nInitializing automated trading pipeline for {ticker}...")
        payloads = [{"ticker": ticker}]
    
    # Build the graph
    app = build_graph()
    
    # Run the graph for all payloads
    print(f"\nInvoking graph execution for {len(payloads)} candidates...")
    for i, payload in enumerate(payloads, 1):
        ticker = payload["ticker"]
        print(f"\n--- Processing Candidate #{i}: {ticker} ---")
        start_time = time.time()
        final_state = app.invoke(payload)
        end_time = time.time()
        
        print("\n" + "="*50)
        print(f"FINAL PIPELINE OUTPUT FOR {ticker}")
        print("="*50)
        print("Ticker:", final_state.get("ticker"))
        print("\n--- Final Report ---")
        print(final_state.get("final_report"))
        print("="*50 + "\n")
        
        # Persist all data
        persist_pipeline_results(final_state, start_time, end_time)
    
    # Clean up at the very end
    from src.data.nse_fetcher import cleanup_cache
    cleanup_cache()

if __name__ == "__main__":
    main()
