import json
import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.news_fetcher import fetch_latest_announcements

def test_single_stock_fetch():
    ticker = "RELIANCE"
    print(f"Testing fetch_latest_announcements for {ticker}...")
    
    # Limit to 1 to just grab the most recent relevant earnings/board meeting
    results = fetch_latest_announcements(ticker, limit=1)
    
    output_path = os.path.join(os.path.dirname(__file__), "news_output.json")
    with open(output_path, "w") as f:
        json.dump(results, f, indent=4)
        
    print(f"\n✅ Test complete! Found {len(results)} relevant announcements.")
    print(f"Saved extracted data and Long-Term POV to: {output_path}")
    
    if results:
        print("\n--- Extracted Long-Term POV ---")
        print(results[0].get("text_content", "No content extracted."))
    else:
        print("\n⚠️ No 'Outcome of Board Meeting' found in recent history for this stock.")

if __name__ == "__main__":
    test_single_stock_fetch()
