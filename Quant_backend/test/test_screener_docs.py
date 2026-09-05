import sys
import os
import json
import pytest

# Add Quant_backend to sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data.screener_in_client import (
    get_screener_documents_sync,
    get_screener_data_sync,
    get_peers_sync
)
from src.data.news_fetcher import download_and_parse_pdf

def test_screener_documents_tcs():
    print("\n--- Testing Screener Documents for TCS ---")
    docs = get_screener_documents_sync("TCS")
    assert docs is not None
    assert docs.get("symbol") == "TCS"
    assert "Tata Consultancy" in docs.get("company_name", "")
    
    # Check Annual Reports
    ar_list = docs.get("annual_reports", [])
    print(f"Annual Reports found: {len(ar_list)}")
    assert len(ar_list) > 0, "Expected at least one annual report"
    latest_ar = ar_list[0]
    print(f"Latest AR: {latest_ar.get('title')} -> {latest_ar.get('url')}")
    assert "Annual Report" in latest_ar.get("title", "")
    assert latest_ar.get("url", "").startswith("http")
    
    # Check Announcements
    ann_list = docs.get("announcements", [])
    print(f"Corporate Announcements found: {len(ann_list)}")
    assert len(ann_list) > 0, "Expected at least one corporate announcement"
    latest_ann = ann_list[0]
    print(f"Latest Announcement: {latest_ann.get('title')} ({latest_ann.get('date')}) -> {latest_ann.get('attachment')}")
    
    # Check Concalls
    cc_list = docs.get("concalls", [])
    print(f"Concalls found: {len(cc_list)}")
    assert len(cc_list) > 0, "Expected concalls to be present"
    latest_cc = cc_list[0]
    print(f"Latest Concall: {latest_cc.get('period')}")

def test_bse_pdf_download():
    print("\n--- Testing Direct PDF Download from BSE ---")
    docs = get_screener_documents_sync("TCS")
    ann_with_pdf = next((a for a in docs.get("announcements", []) if a.get("attachment") and a["attachment"].endswith(".pdf")), None)
    if ann_with_pdf:
        pdf_url = ann_with_pdf["attachment"]
        print(f"Downloading PDF from {pdf_url}...")
        text = download_and_parse_pdf(pdf_url)
        print(f"Downloaded and extracted {len(text)} characters.")
        assert len(text) > 50, "Expected non-empty text from BSE PDF"
    else:
        print("No announcement with direct .pdf attachment found in recent items.")

def test_screener_fundamentals_tcs():
    print("\n--- Testing Screener Fundamentals & Context for TCS ---")
    fund = get_screener_data_sync("TCS")
    assert fund is not None
    ratios = fund.get("ratios", {})
    print(f"Ratios found: {len(ratios)}")
    assert "Market Cap" in ratios or "Current Price" in ratios, "Expected key ratios"
    print("Sample ratios:", {k: ratios[k] for k in list(ratios.keys())[:4]})
    assert "documents" in fund, "Expected documents to be attached to fundamentals"

if __name__ == "__main__":
    test_screener_documents_tcs()
    test_bse_pdf_download()
    test_screener_fundamentals_tcs()
    print("\n✅ All Screener document & filing tests passed successfully!")
