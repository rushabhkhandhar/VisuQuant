import json
import requests
import time
import fitz  # PyMuPDF
import ollama

def summarize_text_with_llm(raw_text: str) -> str:
    """Uses the local LLM to perform strict extractive summarization, avoiding hallucinations."""
    if not raw_text or len(raw_text.strip()) < 50:
        return "No substantial text found to summarize."

    # Keep only the first ~4000 characters to avoid context window blowouts 
    # and mostly capture the core press release which is usually at the start or early pages.
    truncated_text = raw_text[:4000]

    prompt = f"""
    You are a strict financial data extractor. 
    Your ONLY job is to extract facts from the provided text.
    
    RULES:
    1. DO NOT calculate, infer, guess, or hallucinate any numbers or facts.
    2. If a metric is not explicitly stated in the text, do not mention it.
    3. Ignore all boilerplate legal addresses to the BSE/NSE, "Dear Sir/Madam", etc.
    4. You MUST output exactly 2-3 concise bullet points starting with a dash (-). Do not output paragraphs.
    5. NEVER repeat the input text verbatim. If the text is just a routine administrative cover letter with no actual news or financial figures, output exactly: "- Routine administrative filing with no material updates."

    TEXT TO SUMMARIZE:
    <text>
    {truncated_text}
    </text>
    """

    try:
        response = ollama.chat(
            model='qwen2.5vl:7b',
            messages=[{'role': 'user', 'content': prompt}],
            options={'temperature': 0.0} # Zero temperature for deterministic, factual output
        )
        return response['message']['content'].strip()
    except Exception as e:
        print(f"Error during LLM summarization: {e}")
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
            for page_num in range(min(3, len(pdf_document))):
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
            # Process the latest announcements
            for item in data[:limit]:
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
