import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.graph import build_graph
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
    ensure_ollama_running()

    if len(sys.argv) > 1:
        ticker = sys.argv[1].upper()
    else:
        # Fallback for IDE runners that don't pass args
        ticker = input("Enter ticker symbol (e.g. RELIANCE): ").strip().upper()
        if not ticker:
            raise ValueError("Ticker symbol cannot be empty!")
            
    print(f"Initializing automated trading pipeline for {ticker}...")
    
    # Build the graph
    app = build_graph()
    
    # Initial state
    initial_state = {
        "ticker": ticker
    }
    
    # Run the graph
    print("Invoking graph execution...")
    final_state = app.invoke(initial_state)
    
    print("\n" + "="*50)
    print(f"FINAL PIPELINE OUTPUT FOR {ticker}")
    print("="*50)
    print("Ticker:", final_state.get("ticker"))
    print("Chart Image Path:", final_state.get("chart_image_path"))
    print("\n--- Scraped Data ---")
    print(final_state.get("scraped_data"))
    print("\n--- Vision Analysis ---")
    print(final_state.get("vision_analysis"))
    print("\n--- Final Decision ---")
    print(final_state.get("final_decision"))
    print("="*50 + "\n")

if __name__ == "__main__":
    main()
