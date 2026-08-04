import json
import requests
import time
import os
import fitz  # PyMuPDF
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
    Your ONLY job is to extract hard financial facts and structural updates from the provided text, focusing on the Long-Term Point of View (POV).
    
    RULES:
    1. DO NOT calculate, infer, guess, or hallucinate any numbers or facts. If a number is not explicitly written, DO NOT output it.
    2. You MUST extract key financial metrics if present (e.g., Total Revenue, Net Profit, EPS, EBITDA, Year-over-Year % growth, or margins).
    3. Include structural investing impact (e.g., debt reduction, strategic expansion plans, guidance, capital expenditure).
    4. Ignore short-term noise and boilerplate legal text.
    5. You MUST output exactly 4-6 concise bullet points starting with a dash (-). Ensure at least 1-2 bullet points contain hard financial numbers.
    6. NEVER repeat the input text verbatim.

    TEXT TO SUMMARIZE:
    <text>
    {truncated_text}
    </text>
    """

    try:
        api_keys_str = os.environ.get("GEMINI_API_KEYS", "")
        if not api_keys_str:
            return "Error: GEMINI_API_KEYS not found in .env."
            
        # Use the first key for VisuQuant fetching
        api_key = api_keys_str.split(",")[0].strip()
        
        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent?key={api_key}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        
        res = requests.post(url, headers=headers, json=payload, timeout=30)
        if res.status_code == 200:
            data = res.json()
            return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        else:
            print(f"Gemini API Error {res.status_code}: {res.text}")
            return "Summary failed due to API error."
            
    except Exception as e:
        print(f"Error during Gemini summarization: {e}")
        return "Summary failed. Showing raw snippet: " + truncated_text[:200]

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

def fetch_latest_announcements(ticker: str, limit: int = 3) -> list:
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
            
            # Filter for relevant announcements only
            relevant_anns = []
            for item in data:
                title = (item.get('subject') or item.get('desc') or '').lower()
                if "outcome of board meeting" in title or "financial result" in title:
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
                
    except Exception as e:
        print(f"[{ticker}] Error fetching announcements: {e}")
        
    return announcements
