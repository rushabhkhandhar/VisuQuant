import json
import requests
import time
import os
import re
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
        "gemini-flash-latest",
        "gemini-flash-lite-latest"
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
                print(f"Warning: {model_name} returned {res.status_code}: {res.text[:100]}. Falling back to next model...")
                continue
            else:
                print(f"Gemini API Error {res.status_code} on {model_name}: {res.text[:100]}")
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
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/pdf,text/html,*/*"
    }
    try:
        res = requests.get(pdf_url, headers=headers, timeout=12)
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
from src.data.screener_in_client import get_screener_documents_sync

def fetch_latest_announcements(ticker: str, limit: int = 3, as_of_date: str = None, screener_docs: dict = None) -> list:
    """
    Fetch corporate announcements, latest annual reports, and concall transcripts.
    Uses Screener.in (and BSE India direct filings) to prevent GitHub Actions / cloud 403 blocks.
    """
    announcements = []
    target_date = None
    if as_of_date and as_of_date != date.today().strftime("%Y-%m-%d"):
        try:
            target_date = datetime.strptime(as_of_date, "%Y-%m-%d")
        except Exception:
            pass

    # 1. Fetch documents via Screener.in (Playwright) if not passed in
    try:
        if screener_docs is None:
            print(f"[{ticker}] Fetching documents and filings via Screener.in...")
            screener_docs = get_screener_documents_sync(ticker)
        
        # A. Process Latest Corporate Announcements
        screener_anns = screener_docs.get("announcements", [])
        print(f"[{ticker}] Retrieved {len(screener_anns)} announcements from Screener.in.")
        
        count = 0
        for item in screener_anns:
            ann_date_str = item.get("date", "")
            if target_date and ann_date_str:
                try:
                    # e.g., "5 Sep 2026" or "5 Sep"
                    clean_date_str = ann_date_str if re.search(r'20\d\d', ann_date_str) else f"{ann_date_str} {datetime.now().year}"
                    ann_dt = datetime.strptime(clean_date_str, "%d %b %Y")
                    if ann_dt > target_date:
                        continue
                except Exception:
                    pass

            ann = {
                "date": item.get("date") or datetime.today().strftime("%d-%b-%Y"),
                "title": item.get("title") or item.get("description", "")[:80],
                "description": item.get("description", ""),
                "attachment": item.get("attachment") or "",
                "text_content": ""
            }

            # If there's a PDF attachment, fetch, parse, and summarize it
            if ann["attachment"] and (ann["attachment"].endswith('.pdf') or 'AnnPdfOpen' in ann["attachment"]):
                try:
                    extracted_text = download_and_parse_pdf(ann["attachment"])
                    if extracted_text:
                        print(f"[{ticker}] Summarizing announcement from {ann['date']}...")
                        ann["text_content"] = summarize_text_with_llm(extracted_text)
                except Exception as ex:
                    print(f"[{ticker}] Failed to parse/summarize PDF: {ex}")

            announcements.append(ann)
            count += 1
            if count >= limit:
                break

        # B. Inject Latest Annual Report
        annual_reports = screener_docs.get("annual_reports", [])
        if annual_reports:
            latest_ar = annual_reports[0]
            print(f"[{ticker}] Injected latest annual report: {latest_ar.get('title')} ({latest_ar.get('year')})")
            announcements.append({
                "date": latest_ar.get("year") or datetime.today().strftime("%Y"),
                "title": f"Annual Report: {latest_ar.get('title', 'Latest Annual Report')}",
                "description": f"Official Audited Annual Report filing from BSE/Screener.",
                "attachment": latest_ar.get("url") or "",
                "text_content": {
                    "short_term_pov": [f"Official Annual Report ({latest_ar.get('year')}) available for audit review."],
                    "long_term_pov": [f"Full-year audited statutory financial statements, notes, and management discussion."]
                }
            })

        # C. Inject Latest Concall / Investor Presentation
        concalls = screener_docs.get("concalls", [])
        if concalls:
            latest_cc = concalls[0]
            cc_url = latest_cc.get("transcript_url") or latest_cc.get("ppt_url") or ""
            print(f"[{ticker}] Injected latest earnings concall: {latest_cc.get('period')}")
            
            cc_content = {
                "short_term_pov": [f"Quarterly earnings conference call ({latest_cc.get('period')}) filed."],
                "long_term_pov": ["Management commentary on operational runway, margins, and industry tailwinds."]
            }
            # Attempt to parse transcript if PDF
            if cc_url and (cc_url.endswith('.pdf') or 'AnnPdfOpen' in cc_url):
                try:
                    cc_text = download_and_parse_pdf(cc_url)
                    if cc_text:
                        cc_content = summarize_text_with_llm(cc_text)
                except Exception:
                    pass

            announcements.append({
                "date": latest_cc.get("period") or datetime.today().strftime("%b %Y"),
                "title": f"Earnings Concall ({latest_cc.get('period')})",
                "description": f"Management earnings conference call transcript and presentation.",
                "attachment": cc_url,
                "text_content": cc_content
            })

    except Exception as e:
        print(f"[{ticker}] Error fetching documents via Screener.in: {e}")

    # 2. Fallback to NSE only if Screener returned nothing
    if not announcements:
        print(f"[{ticker}] Screener returned no documents. Trying NSE fallback...")
        try:
            url = f"https://www.nseindia.com/api/corporate-announcements?index=equities&symbol={ticker}"
            homepage = "https://www.nseindia.com"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Connection": "keep-alive"
            }
            session = requests.Session()
            session.headers.update(headers)
            session.get(homepage, timeout=5)
            time.sleep(1)
            res = session.get(url, timeout=5)
            if res.status_code == 200:
                data = res.json()
                for item in data[:limit]:
                    announcements.append({
                        "date": item.get('an_dt'),
                        "title": item.get('subject') or item.get('desc'),
                        "description": item.get('desc'),
                        "attachment": item.get('attchmntFile'),
                        "text_content": ""
                    })
        except Exception as nse_err:
            print(f"[{ticker}] NSE fallback also failed/blocked: {nse_err}")

    # 3. Add Google News Headlines Sentiment
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
            if target_date and pubDate:
                try:
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

    return announcements

