import json
import requests
import time
import os
import fitz  # PyMuPDF
import urllib.request
import xml.etree.ElementTree as ET
from dotenv import load_dotenv

load_dotenv()

def summarize_text_with_llm(raw_text: str) -> str:
    """Uses the LLM to perform strict extractive summarization, focusing on Long Term POV."""
    if not raw_text or len(raw_text.strip()) < 50:
        return "No substantial text found to summarize."

    # We will pass the full text since Gemini can easily handle large context windows.
    # The actual financial numbers are rarely on the first 3 pages (which are just cover letters).
    truncated_text = raw_text

    prompt = f"""
    You are a strict financial data extractor. 
    Your ONLY job is to extract hard financial facts and structural updates from the provided text, categorizing them into Short-Term and Long-Term Points of View (POV).
    
    RULES:
    1. DO NOT calculate, infer, guess, or hallucinate any numbers or facts. If a number is not explicitly written, DO NOT output it.
    2. Short-Term POV: Extract key financial metrics (e.g., Total Revenue, Net Profit, EPS, EBITDA, Year-over-Year % growth, margins) and immediate market catalysts (dividends, management changes).
    3. Long-Term POV: Extract structural investing impacts (e.g., debt reduction, strategic expansion plans, guidance, capital expenditure, acquisitions).
    4. Ignore noise and boilerplate legal text.
    5. You MUST output EXACTLY valid JSON matching this schema:
    {{
      "short_term_pov": ["bullet 1", "bullet 2"],
      "long_term_pov": ["bullet 1", "bullet 2"]
    }}
    6. Do not include markdown formatting (like ```json). Just the raw JSON object.
    
    TEXT TO SUMMARIZE:
    <text>
    {truncated_text}
    </text>
    """

    api_keys_str = os.environ.get("GEMINI_API_KEYS", "")
    if not api_keys_str:
        return "Error: GEMINI_API_KEYS not found in .env."
        
    # Use the first key for VisuQuant fetching
    api_key = api_keys_str.split(",")[0].strip()
    
    models_to_try = [
            "gemini-3.6-flash",
            "gemini-3.5-flash-lite",
            "gemini-1.5-flash"
    ]
    
    headers = {"Content-Type": "application/json"}
    payload = {
        "contents": [{"parts": [{"text": prompt}]}]
    }
    
    for model_name in models_to_try:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
            
            res = requests.post(url, headers=headers, json=payload, timeout=60)
            if res.status_code == 200:
                data = res.json()
                raw_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                
                # Clean markdown backticks if the model ignores instruction 6
                if raw_text.startswith("```json"):
                    raw_text = raw_text[7:]
                if raw_text.startswith("```"):
                    raw_text = raw_text[3:]
                if raw_text.endswith("```"):
                    raw_text = raw_text[:-3]
                    
                import json_repair
                return json_repair.loads(raw_text.strip())
                
            elif res.status_code in [503, 429, 404, 400]:
                print(f"Warning: {model_name} returned {res.status_code}: {res.text}. Falling back to next model...")
                continue
            else:
                print(f"Gemini API Error {res.status_code} on {model_name}: {res.text}")
                continue
                
        except requests.exceptions.Timeout:
            print(f"Warning: Model {model_name} timed out. Falling back to next model...")
            continue
        except Exception as e:
            print(f"Error calling {model_name}: {e}")
            continue
            
    return {"error": f"Summary failed. All models failed or timed out. Showing raw snippet: {truncated_text[:200]}"}

def download_and_parse_pdf(pdf_url: str) -> str:
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/pdf"
    }
    try:
        res = requests.get(pdf_url, headers=headers, timeout=10)
        if res.status_code == 200:
            pdf_document = fitz.open(stream=res.content, filetype="pdf")
            text = ""
            for page_num in range(min(15, len(pdf_document))):
                page = pdf_document.load_page(page_num)
                text += page.get_text("text") + "\n"
            return text.strip()
    except Exception as e:
        print(f"Error parsing PDF: {e}")
    return ""

from datetime import datetime, date

def fetch_latest_announcements(ticker: str, limit: int = 3, as_of_date: str = None) -> list:
    """Fetch the latest corporate announcements and extract PDF text."""
    url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={ticker}"
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
        session.get(homepage, timeout=10)
        time.sleep(2)
        
        api_headers = headers.copy()
        api_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        api_headers["X-Requested-With"] = "XMLHttpRequest"
        api_headers["Referer"] = f"https://www.nseindia.com/get-quote/equity?symbol={ticker}"
        
        res = session.get(url, headers=api_headers, timeout=10)
        
        if res.status_code == 200:
            data = res.json()
            
            # Filter for relevant announcements only (Board Meetings, Financials, Transcripts)
            relevant_anns = []
            
            target_date = None
            if as_of_date and as_of_date != date.today().strftime("%Y-%m-%d"):
                target_date = datetime.strptime(as_of_date, "%Y-%m-%d")
                
            for item in data:
                # Discard future announcements if doing historical time-travel
                if target_date and item.get('an_dt'):
                    try:
                        # Format is usually '29-Jul-2026 18:29:49'
                        ann_date = datetime.strptime(item.get('an_dt'), "%d-%b-%Y %H:%M:%S")
                        if ann_date > target_date:
                            continue
                    except Exception:
                        pass # if parsing fails, assume it's safe or discard? Let's assume safe to avoid missing data, though it might bleed future.
                        
                title = (item.get('subject') or item.get('desc') or '').lower()
                if "outcome of board meeting" in title or "financial result" in title or "transcript" in title:
                    relevant_anns.append(item)
                    if len(relevant_anns) >= limit:
                        break
                        
            # Process the filtered announcements
            for item in relevant_anns:
                ann = {
                    "date": item.get('an_dt'),
                    "title": item.get('subject') or item.get('desc'),
                    "description": item.get('desc'),
                    "attachment": item.get('attchmntFile'),
                    "text_content": ""
                }
                
                # If there's a PDF attachment, fetch, parse, and summarize it
                if ann["attachment"] and ann["attachment"].endswith('.pdf'):
                    extracted_text = download_and_parse_pdf(ann["attachment"])
                    if extracted_text:
                        print(f"[{ticker}] Summarizing announcement from {ann['date']}...")
                        ann["text_content"] = summarize_text_with_llm(extracted_text)
                    
                announcements.append(ann)
                
        # --- Add Google News Headlines ---
        print(f"[{ticker}] Fetching latest Google News headlines...")
        try:
            url_news = f'https://news.google.com/rss/search?q={ticker}+stock+NSE&hl=en-IN&gl=IN&ceid=IN:en'
            req = urllib.request.Request(url_news, headers={'User-Agent': 'Mozilla/5.0'})
            rss_data = urllib.request.urlopen(req, timeout=10).read()
            root = ET.fromstring(rss_data)
            
            headlines_text = ""
            count = 0
            for item in root.findall('.//item'):
                pubDate = item.find('pubDate').text if item.find('pubDate') is not None else ''
                
                # Check date for time-travel
                if target_date and pubDate:
                    try:
                        # RSS date format: 'Tue, 04 Aug 2026 10:00:00 GMT'
                        news_date = datetime.strptime(pubDate, "%a, %d %b %Y %H:%M:%S %Z")
                        if news_date > target_date:
                            continue
                    except Exception:
                        pass
                
                title = item.find('title').text if item.find('title') is not None else ''
                headlines_text += f"- {title} ({pubDate})\n"
                
                count += 1
                if count >= 5:
                    break
                
            if headlines_text.strip():
                print(f"[{ticker}] Summarizing Google News headlines...")
                google_ann = {
                    "date": time.strftime("%d-%b-%Y %H:%M:%S"),
                    "title": f"Latest Google News Headlines for {ticker}",
                    "description": "Aggregated recent news articles and market sentiment.",
                    "attachment": "",
                    "text_content": summarize_text_with_llm(f"LATEST GOOGLE NEWS HEADLINES:\n{headlines_text}")
                }
                announcements.append(google_ann)
        except Exception as e:
            print(f"[{ticker}] Error fetching Google News: {e}")
                
    except Exception as e:
        print(f"[{ticker}] Error fetching announcements: {e}")
        
    return announcements
