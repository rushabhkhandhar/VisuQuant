import json
import requests
import time

def get_nse_announcements(ticker: str):
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
    
    try:
        print("Hitting homepage for cookies...")
        session.get(homepage, timeout=10)
        time.sleep(2)
        
        print("Fetching announcements API...")
        api_headers = headers.copy()
        api_headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
        api_headers["X-Requested-With"] = "XMLHttpRequest"
        api_headers["Referer"] = f"https://www.nseindia.com/get-quote/equity?symbol={ticker}"
        
        res = session.get(url, headers=api_headers, timeout=10)
        print(f"Status: {res.status_code}")
        
        if res.status_code == 200:
            return res.json()
        else:
            print(f"Response: {res.text[:200]}")
    except Exception as e:
        print(f"Error: {e}")
        
    return None

import fitz  # PyMuPDF
import io

def download_and_parse_pdf(pdf_url: str):
    print(f"Downloading PDF from {pdf_url}...")
    headers = {
        "User-Agent": "Mozilla/5.0",
        "Accept": "application/pdf"
    }
    try:
        res = requests.get(pdf_url, headers=headers, timeout=10)
        if res.status_code == 200:
            print("PDF downloaded successfully. Parsing...")
            # Load PDF from memory
            pdf_document = fitz.open(stream=res.content, filetype="pdf")
            text = ""
            # Extract text from first 3 pages to avoid massive text dumps
            for page_num in range(min(3, len(pdf_document))):
                page = pdf_document.load_page(page_num)
                text += page.get_text("text") + "\n"
            return text.strip()
        else:
            print(f"Failed to download PDF. Status: {res.status_code}")
    except Exception as e:
        print(f"Error parsing PDF: {e}")
    return None

if __name__ == "__main__":
    data = get_nse_announcements("MTARTECH")
    if data:
        print(f"Found {len(data)} items.")
        
        # Get the first one with a PDF attachment
        pdf_item = next((item for item in data if item.get('attchmntFile') and item.get('attchmntFile').endswith('.pdf')), None)
        
        if pdf_item:
            print("\nLatest Announcement with PDF:")
            print("Date:", pdf_item.get('an_dt'))
            print("Desc:", pdf_item.get('desc'))
            print("Attachment:", pdf_item.get('attchmntFile'))
            
            pdf_text = download_and_parse_pdf(pdf_item.get('attchmntFile'))
            if pdf_text:
                print("\n--- Extracted Text (First 1000 chars) ---")
                print(pdf_text[:1000])
                print("---------------------------------------")
        else:
            print("No PDF announcements found.")

