import os
import time
import json
import requests
from datetime import datetime
import pytz
from dotenv import load_dotenv

load_dotenv()

# Configuration
POLL_INTERVAL_SECONDS = 60
CACHE_FILE = "monitor_state.json"

def send_telegram_alert(message: str) -> bool:
    """Sends a basic push notification to Telegram."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram credentials not found in .env. Skipping notification.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error sending Telegram alert: {e}")
        return False

def fetch_latest_announcements(limit: int = 20) -> list:
    """Fetches raw announcements across ALL equities without any AI/LLM summarization."""
    url = "https://www.nseindia.com/api/corporate-announcements?index=equities"
    homepage = "https://www.nseindia.com"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "Connection": "keep-alive"
    }
    
    session = requests.Session()
    session.headers.update(headers)
    
    announcements = []
    
    try:
        # NSE requires a visit to the homepage first to set cookies
        session.get(homepage, timeout=10)
        time.sleep(1)
        
        api_headers = headers.copy()
        api_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        api_headers["X-Requested-With"] = "XMLHttpRequest"
        api_headers["Referer"] = "https://www.nseindia.com/market-data/corporate-announcements"
        
        res = session.get(url, headers=api_headers, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            for item in data[:limit]:
                announcements.append({
                    "id": str(item.get('seq_id', item.get('an_dt'))),  # Unique identifier
                    "symbol": item.get('symbol', 'UNKNOWN'),
                    "date": item.get('an_dt'),
                    "title": item.get('subject') or item.get('desc'),
                    "attachment": item.get('attchmntFile')
                })
    except Exception as e:
        print(f"Error fetching announcements: {e}")
        
    return announcements

def is_market_open() -> bool:
    """Check if current IST time is between 9:00 AM and 3:30 PM on weekdays."""
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
    
    # 0 = Monday, 4 = Friday. 5 and 6 are weekend
    if now.weekday() > 4:
        return False
        
    market_open = now.replace(hour=9, minute=0, second=0, microsecond=0)
    market_close = now.replace(hour=15, minute=30, second=0, microsecond=0)
    
    return market_open <= now <= market_close

def load_cache() -> set:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r') as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_cache(seen_ids: set):
    with open(CACHE_FILE, 'w') as f:
        json.dump(list(seen_ids), f)

def start_monitor():
    print("🚀 Starting Global Live News Monitor for ALL NSE Equities...")
    print(f"Polling interval: {POLL_INTERVAL_SECONDS} seconds.")
    
    seen_ids = load_cache()
    
    while True:
        if not is_market_open():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Market is closed. Sleeping...")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking NSE for global announcements...")
        announcements = fetch_latest_announcements()
        
        new_news_found = False
        
        for ann in announcements:
            ann_id = ann['id']
            if ann_id not in seen_ids:
                # We found new news!
                new_news_found = True
                seen_ids.add(ann_id)
                
                # Format message
                symbol = ann['symbol']
                message = f"🚨 <b>NEW NSE ALERT: {symbol}</b>\n\n"
                message += f"<b>Title:</b> {ann['title']}\n"
                message += f"<b>Date:</b> {ann['date']}\n"
                
                if ann['attachment']:
                    message += f"\n🔗 <a href='{ann['attachment']}'>View PDF Attachment</a>"
                
                print(f"⚠️ NEW ANNOUNCEMENT FOR {symbol}! Sending to Telegram...")
                send_telegram_alert(message)
                
        if new_news_found:
            save_cache(seen_ids)
            
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    start_monitor()
