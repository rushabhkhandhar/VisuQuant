import os
import io
import time
import json
import requests
import textwrap
import tempfile
from datetime import datetime
import pytz
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont
import pdfplumber
import threading
from itertools import cycle
from http.server import BaseHTTPRequestHandler, HTTPServer

load_dotenv()

# We will load multiple keys from GEMINI_API_KEYS or fallback to GEMINI_API_KEY
keys_str = os.environ.get("GEMINI_API_KEYS") or os.environ.get("GEMINI_API_KEY")
if keys_str:
    API_KEYS_POOL = [k.strip() for k in keys_str.split(",") if k.strip()]
else:
    API_KEYS_POOL = []

key_iterator = cycle(API_KEYS_POOL) if API_KEYS_POOL else None
key_lock = threading.Lock()

def get_next_api_key():
    if not key_iterator:
        return None
    with key_lock:
        return next(key_iterator)

class RateLimiter:
    def __init__(self):
        self.pause_until = 0
        self.lock = threading.Lock()

    def wait_if_needed(self):
        # We don't hold the lock while sleeping so other threads can also wait simultaneously
        with self.lock:
            sleep_time = self.pause_until - time.time()
        
        if sleep_time > 0:
            time.sleep(sleep_time)

    def set_pause(self, seconds):
        with self.lock:
            new_pause = time.time() + seconds
            if new_pause > self.pause_until:
                self.pause_until = new_pause

global_rate_limiter = RateLimiter()

# Configuration
POLL_INTERVAL_SECONDS = 60
CACHE_FILE = "monitor_state.json"

def download_and_extract_text(pdf_url: str) -> str:
    if not pdf_url: 
        return ""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        }
        response = requests.get(pdf_url, headers=headers, timeout=20)
        if response.status_code == 200:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                tmp.write(response.content)
                tmp_path = tmp.name
            
            text = ""
            with pdfplumber.open(tmp_path) as pdf:
                # Only read first 3 pages to avoid huge prompts
                for page in pdf.pages[:3]:
                    extracted = page.extract_text()
                    if extracted:
                        text += extracted + "\n"
                    
            os.remove(tmp_path)
            return text
        return ""
    except Exception as e:
        print(f"Error extracting PDF: {e}")
        return ""

def extract_financial_numbers_with_llm(text: str) -> str:
    if not text.strip():
        return "No text could be extracted from the PDF."
    
    if not API_KEYS_POOL:
        return "GEMINI_API_KEYS is missing from .env."
        
    prompt = f"""
    You are a financial analyst. Review the following text extracted from a corporate announcement PDF from the National Stock Exchange of India.
    Extract the key financial numbers and highlights (such as Revenue, Net Profit, EPS, EBITDA, YoY Growth, or any major strategic updates) and summarize them cleanly in a few bullet points. 
    Keep it concise and ready to be sent as a Telegram alert. Use bold text (HTML tags <b></b>) for the most important numbers. Do NOT use markdown like **bold**, use ONLY HTML <b> tags.
    If the announcement is not about financial results, summarize the main purpose of the announcement concisely.
    
    PDF Text:
    {text[:10000]}
    """
    
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2}
    }
    
    max_retries = 5
    for attempt in range(max_retries):
        global_rate_limiter.wait_if_needed()
        
        api_key = get_next_api_key()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
        
        try:
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=25)
            if response.status_code == 200:
                data = response.json()
                try:
                    content = data['candidates'][0]['content']['parts'][0]['text']
                    return content.replace("**", "")
                except (KeyError, IndexError):
                    return "Failed to parse AI response structure."
            elif response.status_code == 429:
                # Parse exact retryDelay from Google's response
                sleep_time = 65
                try:
                    error_data = response.json()
                    for detail in error_data.get("error", {}).get("details", []):
                        if "retryDelay" in detail:
                            delay_str = detail["retryDelay"].replace("s", "")
                            # Add a generous 10s buffer because Google's sliding window is very strict
                            sleep_time = float(delay_str) + 10
                except:
                    pass
                
                print(f"⏳ API is busy (Rate Limit). Pausing extraction for {sleep_time:.0f}s before retrying...")
                global_rate_limiter.set_pause(sleep_time)
                
            else:
                print(f"Gemini API Error {response.status_code}: {response.text}")
                return f"AI API Error: {response.status_code}"
        except Exception as e:
            print(f"Error calling Gemini REST API: {e}")
            return "Failed to extract key metrics using AI."
            
    return "AI API Error: Rate Limit Exceeded (429) across all configured keys."

def send_telegram_alert(symbol: str, title: str, date: str, attachment_url: str, extracted_info: str = "") -> bool:
    """Sends a text-based alert to Telegram with extracted information."""
    bot_token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    
    if not bot_token or not chat_id:
        print("⚠️ Telegram credentials not found in .env.")
        return False
        
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    
    caption = f"🚨 <b>{symbol}</b>\n\n<b>{title}</b>\n\n"
    if extracted_info:
        caption += f"<b>Key Highlights:</b>\n{extracted_info}\n\n"
        
    if attachment_url:
        caption += f"🔗 <a href='{attachment_url}'>View Original PDF</a>"
    
    payload = {
        "chat_id": chat_id,
        "text": caption,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    
    try:
        response = requests.post(url, json=payload, timeout=15)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Error sending Telegram alert: {e}")
        return False

def fetch_latest_announcements(limit: int = 20) -> list:
    """Fetches raw announcements across ALL equities."""
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
                    "id": str(item.get('seq_id', item.get('an_dt'))),
                    "symbol": item.get('symbol', 'UNKNOWN'),
                    "date": item.get('an_dt'),
                    "title": item.get('subject') or item.get('desc'),
                    "attachment": item.get('attchmntFile')
                })
    except Exception as e:
        print(f"Error fetching announcements: {e}")
        
    return announcements



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

def process_single_announcement(ann):
    """Processes a single announcement in a thread-safe manner."""
    print(f"⚠️ NEW ANNOUNCEMENT FOR {ann['symbol']}! Downloading and processing PDF...")
    pdf_text = download_and_extract_text(ann['attachment'])
    extracted_info = extract_financial_numbers_with_llm(pdf_text) if pdf_text else ""
    send_telegram_alert(ann['symbol'], ann['title'], ann['date'], ann['attachment'], extracted_info)
    return ann['id']

def start_monitor():
    print("🚀 Starting Global Live News Monitor (Multi-Key Parallel Mode)...")
    print(f"Polling interval: {POLL_INTERVAL_SECONDS} seconds.")
    print(f"Loaded {len(API_KEYS_POOL)} Gemini API key(s) for load balancing.")
    
    if not API_KEYS_POOL:
        print("⚠️ WARNING: No Gemini API keys found. AI extraction will fail.")
        
    seen_ids = load_cache()
    # Always set is_first_run = True on startup to build a fresh baseline
    # and ignore any backlog of news that arrived while the script was turned off.
    is_first_run = True
    if is_first_run:
        print("📥 Script started: Fetching existing announcements to build baseline...")
    
    while True:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking NSE for global announcements...")
        announcements = fetch_latest_announcements()
        
        new_anns = []
        for ann in reversed(announcements):
            if ann['id'] not in seen_ids:
                new_anns.append(ann)
                
        if is_first_run:
            # Baseline fetch: mark all as seen and skip processing
            for ann in new_anns:
                seen_ids.add(ann['id'])
            if len(seen_ids) > 0:
                print(f"✅ Baseline established ({len(seen_ids)} announcements). Now waiting for NEW announcements...")
                is_first_run = False
                save_cache(seen_ids)
        elif new_anns:
            # Mark all new announcements as seen so we don't process them again
            for ann in new_anns:
                seen_ids.add(ann['id'])
                
            # Filter to ONLY process 'Outcome of Board Meeting'
            filtered_anns = [ann for ann in new_anns if "outcome of board meeting" in ann['title'].lower()]
            
            if filtered_anns:
                print(f"⚡ Detected {len(filtered_anns)} 'Outcome of Board Meeting' announcements! Launching extraction...")
                for ann in filtered_anns:
                    try:
                        process_single_announcement(ann)
                    except Exception as e:
                        print(f"❌ Execution failed for {ann['symbol']}: {e}")
            else:
                print(f"💤 Ignored {len(new_anns)} announcements (not 'Outcome of Board Meeting').")
            
            save_cache(seen_ids)
            
        time.sleep(POLL_INTERVAL_SECONDS)

class DummyHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/plain")
        self.end_headers()
        self.wfile.write(b"Bot is alive and monitoring NSE!")

    def log_message(self, format, *args):
        # Suppress standard HTTP logging to keep the console clean
        pass

def run_dummy_server():
    port = int(os.environ.get("PORT", 8000))
    server = HTTPServer(("0.0.0.0", port), DummyHandler)
    print(f"🌐 Dummy web server listening on port {port} (to satisfy Render.com)")
    server.serve_forever()

if __name__ == "__main__":
    # Start the dummy web server in a background thread so Render doesn't kill the app
    server_thread = threading.Thread(target=run_dummy_server, daemon=True)
    server_thread.start()
    
    start_monitor()
