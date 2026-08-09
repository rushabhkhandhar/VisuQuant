import asyncio
from playwright.async_api import async_playwright
import logging

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
                
            await browser.close()
            
    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol} from screener.in: {e}")
        
    return fundamentals

def get_screener_data_sync(symbol: str) -> dict:
    """Synchronous wrapper for fetch_screener_fundamentals"""
    return asyncio.run(fetch_screener_fundamentals(symbol))

if __name__ == "__main__":
    import json
    data = get_screener_data_sync("SCI")
    print(json.dumps(data, indent=2))
