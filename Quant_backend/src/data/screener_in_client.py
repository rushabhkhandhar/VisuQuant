import asyncio
import logging
import random
import re
from playwright.async_api import async_playwright
from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

async def _extract_documents_from_page(page) -> dict:
    """Helper to extract annual reports, announcements, concalls, and credit ratings from page."""
    docs = {
        "annual_reports": [],
        "announcements": [],
        "concalls": [],
        "credit_ratings": []
    }

    try:
        # 1. Annual Reports
        ar_items = await page.locator("section#documents .annual-reports li a").all()
        for a in ar_items:
            raw = (await a.inner_text()).strip()
            href = await a.get_attribute("href")
            year_match = re.search(r'20\d\d', raw)
            year = year_match.group(0) if year_match else ""
            clean_title = re.sub(r'\s+', ' ', raw.replace("from bse", "").strip())
            docs["annual_reports"].append({
                "title": clean_title,
                "year": year,
                "url": href
            })

        # 2. Corporate Announcements
        ann_div = page.locator("section#documents div.documents:not(.annual-reports):not(.concalls):not(.credit-ratings)")
        if await ann_div.count() > 0:
            ann_items = await ann_div.locator("li").all()
            for item in ann_items:
                links = await item.locator("a").all()
                href = await links[0].get_attribute("href") if links else None
                text = re.sub(r'\s+', ' ', (await item.inner_text()).strip())
                date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s+20\d\d)?)', text)
                date_str = date_match.group(0) if date_match else ""
                title = (await links[0].inner_text()).strip() if links else text[:80]
                docs["announcements"].append({
                    "title": title,
                    "description": text,
                    "date": date_str,
                    "attachment": href
                })

        # 3. Concalls
        cc_items = await page.locator("section#documents .concalls li").all()
        for item in cc_items:
            text = re.sub(r'\s+', ' ', (await item.inner_text()).strip())
            links = {}
            for a in await item.locator("a").all():
                a_name = (await a.inner_text()).strip()
                links[a_name] = await a.get_attribute("href")
            period = re.sub(r'(Transcript|AI Summary|PPT|REC)', '', text).strip()
            docs["concalls"].append({
                "period": period,
                "transcript_url": links.get("Transcript") or links.get("AI Summary"),
                "ppt_url": links.get("PPT"),
                "rec_url": links.get("REC"),
                "links": links
            })

        # 4. Credit Ratings
        cr_items = await page.locator("section#documents .credit-ratings li").all()
        for item in cr_items:
            links = await item.locator("a").all()
            href = await links[0].get_attribute("href") if links else None
            text = re.sub(r'\s+', ' ', (await item.inner_text()).strip())
            docs["credit_ratings"].append({
                "title": text,
                "url": href
            })

    except Exception as e:
        logger.error(f"Error extracting documents from page: {e}")

    return docs


async def fetch_screener_documents(symbol: str) -> dict:
    """
    Fetches annual reports, corporate announcements, concalls, and credit ratings
    from screener.in for a given symbol using Playwright.
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    result = {
        "symbol": symbol,
        "company_name": symbol,
        "annual_reports": [],
        "announcements": [],
        "concalls": [],
        "credit_ratings": []
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            h1_el = page.locator("h1").first
            if await h1_el.count() > 0:
                result["company_name"] = (await h1_el.inner_text()).strip()

            docs = await _extract_documents_from_page(page)
            result.update(docs)

            await browser.close()
    except Exception as e:
        logger.error(f"Error in fetch_screener_documents for {symbol}: {e}")

    return result


def get_screener_documents_sync(symbol: str) -> dict:
    """Synchronous Playwright scraper for Screener.in documents."""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    result = {
        "symbol": symbol,
        "company_name": symbol,
        "annual_reports": [],
        "announcements": [],
        "concalls": [],
        "credit_ratings": []
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)

            h1_el = page.locator("h1").first
            if h1_el.count() > 0:
                result["company_name"] = h1_el.inner_text().strip()

            # 1. Annual Reports
            for a in page.locator("section#documents .annual-reports li a").all():
                raw = a.inner_text().strip()
                href = a.get_attribute("href")
                year_match = re.search(r'20\d\d', raw)
                year = year_match.group(0) if year_match else ""
                clean_title = re.sub(r'\s+', ' ', raw.replace("from bse", "").strip())
                result["annual_reports"].append({
                    "title": clean_title,
                    "year": year,
                    "url": href
                })

            # 2. Announcements
            ann_div = page.locator("section#documents div.documents:not(.annual-reports):not(.concalls):not(.credit-ratings)")
            if ann_div.count() > 0:
                for item in ann_div.locator("li").all():
                    links = item.locator("a").all()
                    href = links[0].get_attribute("href") if links else None
                    text = re.sub(r'\s+', ' ', item.inner_text().strip())
                    date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s+20\d\d)?)', text)
                    date_str = date_match.group(0) if date_match else ""
                    title = links[0].inner_text().strip() if links else text[:80]
                    result["announcements"].append({
                        "title": title,
                        "description": text,
                        "date": date_str,
                        "attachment": href
                    })

            # 3. Concalls
            for item in page.locator("section#documents .concalls li").all():
                text = re.sub(r'\s+', ' ', item.inner_text().strip())
                links = {}
                for a in item.locator("a").all():
                    links[a.inner_text().strip()] = a.get_attribute("href")
                period = re.sub(r'(Transcript|AI Summary|PPT|REC)', '', text).strip()
                result["concalls"].append({
                    "period": period,
                    "transcript_url": links.get("Transcript") or links.get("AI Summary"),
                    "ppt_url": links.get("PPT"),
                    "rec_url": links.get("REC"),
                    "links": links
                })

            # 4. Credit ratings
            for item in page.locator("section#documents .credit-ratings li").all():
                links = item.locator("a").all()
                href = links[0].get_attribute("href") if links else None
                text = re.sub(r'\s+', ' ', item.inner_text().strip())
                result["credit_ratings"].append({
                    "title": text,
                    "url": href
                })

            browser.close()
    except Exception as e:
        logger.error(f"Error in get_screener_documents_sync for {symbol}: {e}")

    return result


async def fetch_screener_fundamentals(symbol: str) -> dict:
    """
    Fetches fundamental data for a given symbol from screener.in using Playwright.
    Extracts Top Ratios, Quarterly Results, Shareholding, and Documents.
    """
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    fundamentals = {
        "symbol": symbol,
        "company_name": symbol,
        "about": "",
        "ratios": {},
        "quarters": {},
        "investors": {},
        "documents": {}
    }

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(user_agent=USER_AGENT)
            page = await context.new_page()

            response = await page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                await page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Company name & About
            h1_el = page.locator("h1").first
            if await h1_el.count() > 0:
                fundamentals["company_name"] = (await h1_el.inner_text()).strip()
            about_el = page.locator(".about p").first
            if await about_el.count() > 0:
                fundamentals["about"] = (await about_el.inner_text()).strip()

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

            # 4. Documents (Annual Reports, Announcements, Concalls)
            fundamentals["documents"] = await _extract_documents_from_page(page)

            await browser.close()
            await asyncio.sleep(random.uniform(1.0, 2.0))

    except Exception as e:
        logger.error(f"Error fetching fundamentals for {symbol} from screener.in: {e}")

    return fundamentals


def get_screener_data_sync(symbol: str) -> dict:
    """Synchronous Playwright scraper for Screener.in fundamentals and documents."""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    fundamentals = {
        "symbol": symbol,
        "company_name": symbol,
        "about": "",
        "ratios": {},
        "quarters": {},
        "investors": {},
        "documents": {}
    }

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)

            # Company name & About
            h1_el = page.locator("h1").first
            if h1_el.count() > 0:
                fundamentals["company_name"] = h1_el.inner_text().strip()
            about_el = page.locator(".about p").first
            if about_el.count() > 0:
                fundamentals["about"] = about_el.inner_text().strip()

            # 1. Ratios
            for item in page.locator("#top-ratios li").all():
                name = item.locator(".name").inner_text()
                number_spans = item.locator(".number").all_inner_texts()
                fundamentals["ratios"][name.strip()] = " / ".join(n.strip() for n in number_spans)

            # Helper for tables
            def extract_table_sync(section_id, max_rows=10):
                table_data = []
                section = page.locator(f"section#{section_id}")
                if section.count() > 0:
                    headers = section.locator("thead th").all_inner_texts()
                    table_data.append([h.strip() for h in headers if h.strip()])
                    rows = section.locator("tbody tr").all()
                    for row in rows[:max_rows]:
                        cells = row.locator("td").all_inner_texts()
                        table_data.append([c.strip() for c in cells if c.strip()])
                return table_data

            fundamentals["quarters"] = extract_table_sync("quarters")
            fundamentals["investors"] = extract_table_sync("shareholding")

            # Documents
            docs = {
                "annual_reports": [],
                "announcements": [],
                "concalls": [],
                "credit_ratings": []
            }

            for a in page.locator("section#documents .annual-reports li a").all():
                raw = a.inner_text().strip()
                href = a.get_attribute("href")
                year_match = re.search(r'20\d\d', raw)
                year = year_match.group(0) if year_match else ""
                clean_title = re.sub(r'\s+', ' ', raw.replace("from bse", "").strip())
                docs["annual_reports"].append({
                    "title": clean_title,
                    "year": year,
                    "url": href
                })

            ann_div = page.locator("section#documents div.documents:not(.annual-reports):not(.concalls):not(.credit-ratings)")
            if ann_div.count() > 0:
                for item in ann_div.locator("li").all():
                    links = item.locator("a").all()
                    href = links[0].get_attribute("href") if links else None
                    text = re.sub(r'\s+', ' ', item.inner_text().strip())
                    date_match = re.search(r'(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)(?:\s+20\d\d)?)', text)
                    date_str = date_match.group(0) if date_match else ""
                    title = links[0].inner_text().strip() if links else text[:80]
                    docs["announcements"].append({
                        "title": title,
                        "description": text,
                        "date": date_str,
                        "attachment": href
                    })

            for item in page.locator("section#documents .concalls li").all():
                text = re.sub(r'\s+', ' ', item.inner_text().strip())
                links = {}
                for a in item.locator("a").all():
                    links[a.inner_text().strip()] = a.get_attribute("href")
                period = re.sub(r'(Transcript|AI Summary|PPT|REC)', '', text).strip()
                docs["concalls"].append({
                    "period": period,
                    "transcript_url": links.get("Transcript") or links.get("AI Summary"),
                    "ppt_url": links.get("PPT"),
                    "rec_url": links.get("REC"),
                    "links": links
                })

            fundamentals["documents"] = docs
            browser.close()

    except Exception as e:
        logger.error(f"Error fetching fundamentals sync for {symbol}: {e}")

    return fundamentals


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
            context = await browser.new_context(user_agent=USER_AGENT)
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
                    if peer_sym != symbol and not peer_sym.isdigit():
                        peers.append(peer_sym)

            await browser.close()
            await asyncio.sleep(random.uniform(1.0, 2.0))

    except Exception as e:
        logger.error(f"Error fetching peers for {symbol} from screener.in: {e}")

    return list(set(peers))


def get_peers_sync(symbol: str) -> list:
    """Synchronous Playwright peer fetcher."""
    url = f"https://www.screener.in/company/{symbol}/consolidated/"
    peers = []

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            context = browser.new_context(user_agent=USER_AGENT)
            page = context.new_page()

            response = page.goto(url, wait_until="domcontentloaded", timeout=15000)
            if response and response.status == 404:
                url = f"https://www.screener.in/company/{symbol}/"
                page.goto(url, wait_until="domcontentloaded", timeout=15000)

            links = page.locator("section#peers tbody tr td a").all()
            for link in links:
                href = link.get_attribute("href")
                if href and href.startswith("/company/"):
                    peer_sym = href.split("/")[2]
                    if peer_sym != symbol and not peer_sym.isdigit():
                        peers.append(peer_sym)

            browser.close()
    except Exception as e:
        logger.error(f"Error in get_peers_sync for {symbol}: {e}")

    return list(set(peers))


if __name__ == "__main__":
    import json
    data = get_screener_data_sync("TCS")
    print(f"Company: {data.get('company_name')}")
    print(f"Ratios: {len(data.get('ratios', {}))}")
    print(f"ARs: {len(data.get('documents', {}).get('annual_reports', []))}")
    print(f"Anns: {len(data.get('documents', {}).get('announcements', []))}")
    print(f"Concalls: {len(data.get('documents', {}).get('concalls', []))}")
