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

load_dotenv()

# We will load the key directly from os.environ when calling the REST API

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
    
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return "GEMINI_API_KEY is missing from .env."
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
    
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
    
    try:
        max_retries = 3
        for attempt in range(max_retries):
            response = requests.post(url, json=payload, headers={'Content-Type': 'application/json'}, timeout=25)
            if response.status_code == 200:
                data = response.json()
                try:
                    content = data['candidates'][0]['content']['parts'][0]['text']
                    return content.replace("**", "")
                except (KeyError, IndexError):
                    return "Failed to parse AI response structure."
            elif response.status_code == 429:
                if attempt < max_retries - 1:
                    print("⚠️ Gemini API Rate Limit Hit (429). Waiting 60 seconds before retrying...")
                    time.sleep(60)
                else:
                    return "AI API Error: Rate Limit Exceeded (429) after retries."
            else:
                print(f"Gemini API Error {response.status_code}: {response.text}")
                return f"AI API Error: {response.status_code}"
    except Exception as e:
        print(f"Error calling Gemini REST API: {e}")
        return "Failed to extract key metrics using AI."

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

def is_market_open() -> bool:
    ist = pytz.timezone('Asia/Kolkata')
    now = datetime.now(ist)
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
    print("🚀 Starting Global Live News Monitor (AI Data Extraction Mode)...")
    print(f"Polling interval: {POLL_INTERVAL_SECONDS} seconds.")
    
    if not os.environ.get("GEMINI_API_KEY"):
        print("⚠️ WARNING: GEMINI_API_KEY not found in .env. AI extraction will fail.")
        
    seen_ids = load_cache()
    # Always set is_first_run = True on startup to build a fresh baseline
    # and ignore any backlog of news that arrived while the script was turned off.
    is_first_run = True
    if is_first_run:
        print("📥 Script started: Fetching existing announcements to build baseline...")
    
    while True:
        if not is_market_open():
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Market is closed. Sleeping...")
            time.sleep(POLL_INTERVAL_SECONDS)
            continue
            
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Checking NSE for global announcements...")
        announcements = fetch_latest_announcements()
        
        new_news_found = False
        
        for ann in reversed(announcements):
            ann_id = ann['id']
            if ann_id not in seen_ids:
                new_news_found = True
                seen_ids.add(ann_id)
                
                if is_first_run:
                    continue
                    
                print(f"⚠️ NEW ANNOUNCEMENT FOR {ann['symbol']}! Downloading and processing PDF...")
                
                pdf_text = download_and_extract_text(ann['attachment'])
                extracted_info = extract_financial_numbers_with_llm(pdf_text) if pdf_text else ""
                
                send_telegram_alert(ann['symbol'], ann['title'], ann['date'], ann['attachment'], extracted_info)
                
                # Sleep to respect Gemini API rate limits (5 RPM free tier)
                print("⏳ Sleeping 15 seconds to avoid API rate limits...")
                time.sleep(15)
                
        if is_first_run and len(seen_ids) > 0:
            print(f"✅ Baseline established ({len(seen_ids)} announcements). Now waiting for NEW announcements...")
            is_first_run = False
            
        if new_news_found:
            save_cache(seen_ids)
            
        time.sleep(POLL_INTERVAL_SECONDS)

if __name__ == "__main__":
    start_monitor()
