from playwright.sync_api import sync_playwright
import base64
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page()
    url = f"https://in.tradingview.com/chart/?symbol=NSE%3ARELIANCE"
    print("Navigating...")
    page.goto(url, wait_until="domcontentloaded", timeout=15000)
    page.wait_for_timeout(5000)
    print("Done")
    browser.close()
