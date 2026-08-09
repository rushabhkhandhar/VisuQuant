import asyncio
from playwright.async_api import async_playwright
import logging
import random

logger = logging.getLogger(__name__)

async def fetch_screener_fundamentals(symbol: str) -> dict:
    """
    Fetches fundamental data for a given symbol from screener.in.
    Extracts Top Ratios, Quarterly Results, and Investor Shareholding.
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    
    fundamentals = {
        "symbol": symbol,
        "ratios": {},
        "quarters": {},
        "investors": {}
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                # Try non-consolidated
                url = f"https://www.screener.in/company/{symbol}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            
            # 1. Ratios
            ratio_items = await page.locator("#top-ratios li").all()
            for item in ratio_items:
                name = await item.locator(".name").inner_text()
                number_spans = await item.locator(".number").all_inner_texts()
                fundamentals["ratios"][name.strip()] = " / ".join(n.strip() for n in number_spans)
            
            # Helper for tables
            async def extract_table(section_id, max_rows=10):
                table_data = []
                section = page.locator(f"section#{section_id}")
                if await section.count() > 0:
                    headers = await section.locator("thead th").all_inner_texts()
                    table_data.append([h.strip() for h in headers if h.strip()])
                    
                    rows = await section.locator("tbody tr").all()
                    for row in rows[:max_rows]:
                        cells = await row.locator("td").all_inner_texts()
                        table_data.append([c.strip() for c in cells if c.strip()])
                return table_data

            # 2. Quarters
            quarters_table = await extract_table("quarters")
            if quarters_table:
                fundamentals["quarters"] = quarters_table
                
            # 3. Investors
            investors_table = await extract_table("shareholding")
            if investors_table:
                fundamentals["investors"] = investors_table
                
            if not fundamentals["ratios"]:
                title = await page.title()
                html = await page.content()
                print(f"DEBUG {symbol} - Ratios empty! Title: {title}")
                with open(f"/Users/rushabhkhandhar/Desktop/Trading/finvison_tech_analysis/Quant_backend/outputs/debug_{symbol}.html", "w") as f:
                    f.write(html)
                    
            await browser.close()
            
            # Anti-bot rate limit delay
            await asyncio.sleep(random.uniform(2.0, 4.0))
            
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol} from screener.in: {e}")
        
    return fundamentals

def get_screener_data_sync(symbol: str) -> dict:
    """Synchronous wrapper for fetch_screener_fundamentals"""
    return asyncio.run(fetch_screener_fundamentals(symbol))

async def fetch_peers(symbol: str) -> list:
    """
    Fetches the peers/competitors for a given symbol from screener.in.
    Returns a list of symbols.
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    peers = []
    
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36"
            )
            page = await context.new_page()
            
            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)
                
            links = await page.locator("section#peers tbody tr td a").all()
            for link in links:
                href = await link.get_attribute("href")
                if href and href.startswith("/company/"):
                    peer_sym = href.split("/")[2]
                    if peer_sym != symbol and not peer_sym.isdigit(): # Exclude self and numeric BSE codes
                        peers.append(peer_sym)
                        
            await browser.close()
            await asyncio.sleep(random.uniform(2.0, 4.0)) ## to avoid rate limit issue 
            
    except Exception as e:
        logger.error(f"Error fetching peers for {symbol} from screener.in: {e}")
        
    return list(set(peers)) # Remove duplicates if any

def get_peers_sync(symbol: str) -> list:
    return asyncio.run(fetch_peers(symbol))

if __name__ == "__main__":
    import json
    data = get_screener_data_sync("SCI")
    print(json.dumps(data, indent=2))
    peers = get_peers_sync("SCI")
    print("Peers:", peers)
