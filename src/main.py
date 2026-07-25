from src.graph import build_graph

def main():
    ticker = "RELIANCE"
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
