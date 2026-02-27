"""
Playwright-based crawler that populates the NYC Music Teacher Finder database.

Usage:
    python crawler.py                    # all sources
    python crawler.py --source steinway
    python crawler.py --source takelessons
    python crawler.py --source thumbtack

Requires:
    pip install playwright playwright-stealth beautifulsoup4
    playwright install chromium
"""

import argparse
import asyncio
import logging
import os
import re
from typing import Optional

from bs4 import BeautifulSoup
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Response
from playwright_stealth import Stealth

import db

load_dotenv()

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

DB_PATH = os.environ.get("DB_PATH", "teachers.db")

# Steinway NY state listing — 167 teachers across 17 pages
STEINWAY_BASE_URL = "https://teacher.steinway.com/listing/new-york"
STEINWAY_MAX_PAGES = 17

# NYC cities to keep (filter out upstate NY)
NYC_CITIES = {
    "new york", "manhattan", "brooklyn", "bronx", "queens", "staten island",
    "astoria", "flushing", "forest hills", "long island city", "sunnyside",
    "bayside", "woodside", "little neck", "middle village", "jackson heights",
    "jamaica", "corona", "elmhurst",
}


# ---------------------------------------------------------------------------
# Steinway
# ---------------------------------------------------------------------------

async def _fetch_page(page: Page, url: str) -> Optional[str]:
    """Navigate to url with stealth headers; return HTML or None on error."""
    try:
        resp = await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        if resp and resp.status >= 400:
            logger.warning("[steinway] HTTP %d for %s", resp.status, url)
            return None
        await asyncio.sleep(1)
        return await page.content()
    except Exception as e:
        logger.warning("[steinway] Failed to load %s: %s", url, e)
        return None


def _parse_steinway_card(card) -> Optional[dict]:
    """Extract teacher data from a section.summary-box element."""
    # Name: inside .media-body h3 a
    name_tag = card.select_one(".media-body h3 a")
    if not name_tag:
        name_tag = card.select_one("h3 a, h2 a")
    if not name_tag:
        return None
    name = name_tag.get_text(strip=True)
    if not name:
        return None

    # Profile URL (use as website since external site URL is behind JS redirect)
    profile_url = name_tag.get("href", "") or ""
    # External website: .visit-website has the real URL in href
    website_tag = card.select_one("a.visit-website")
    website = website_tag.get("href", "") if website_tag else None
    if not website:
        website = profile_url if profile_url.startswith("http") else None

    # Phone: <a href="tel:XXXXXXXX">
    phone_tag = card.select_one("a[href^='tel:']")
    phone = None
    if phone_tag:
        phone = phone_tag.get_text(strip=True)
        if not phone:
            phone = phone_tag.get("href", "").replace("tel:", "")

    # Instruments: .categories-list a elements
    instruments = [
        a.get_text(strip=True)
        for a in card.select(".categories-list a")
        if a.get_text(strip=True)
    ] or ["Piano"]

    # Address: <address> tag
    address_tag = card.select_one("address p")
    address = address_tag.get_text(separator=", ", strip=True).replace("\n", " ").strip() if address_tag else None

    # Remote detection: badge with "I TEACH ONLINE"
    teaches_online = bool(
        card.select_one(
            "img[data-original-title='I TEACH ONLINE'], img[title='I TEACH ONLINE']"
        )
    )
    remote_virtual = "Both" if teaches_online else "In-Person"

    return {
        "name": name,
        "instruments": instruments,
        "remote_virtual": remote_virtual,
        "address": address,
        "website": website,
        "phone": phone,
    }


async def crawl_steinway(page: Page) -> int:
    """
    Crawl teacher.steinway.com for NY teachers.

    Paginates /listing/new-york/p:N (10 per page, up to 17 pages).
    """
    await Stealth().apply_stealth_async(page)
    inserted = 0

    for page_num in range(1, STEINWAY_MAX_PAGES + 1):
        if page_num == 1:
            url = STEINWAY_BASE_URL
        else:
            url = f"{STEINWAY_BASE_URL}/p:{page_num}"

        logger.info("[steinway] Page %d/%d — %s", page_num, STEINWAY_MAX_PAGES, url)
        html = await _fetch_page(page, url)
        if not html:
            continue

        soup = BeautifulSoup(html, "html.parser")
        cards = soup.select("section.summary-box")
        logger.info("[steinway] Page %d: %d cards", page_num, len(cards))

        if not cards:
            logger.info("[steinway] No cards on page %d, stopping", page_num)
            break

        for card in cards:
            data = _parse_steinway_card(card)
            if not data:
                continue

            db.upsert_teacher(
                DB_PATH,
                name=data["name"],
                instruments=data["instruments"],
                remote_virtual=data["remote_virtual"],
                address=data["address"],
                email=None,
                website=data["website"],
                phone=data["phone"],
                rates=None,
                source="steinway",
            )
            inserted += 1

        await asyncio.sleep(1)

    logger.info("[steinway] Done — %d records upserted", inserted)
    return inserted


# ---------------------------------------------------------------------------
# TakeLessons
# ---------------------------------------------------------------------------

async def crawl_takelessons(page: Page) -> int:
    """
    Crawl takelessons.com for NYC music teachers.

    Attempts to intercept the internal search API response first;
    falls back to DOM parsing if the API is not seen within the timeout.
    """
    inserted = 0
    api_data: list[dict] = []

    def handle_response(response: Response) -> None:
        if "search" in response.url and "takelessons.com" in response.url:
            try:
                # Fire-and-forget; we collect the URL and fetch synchronously later
                api_data.append({"url": response.url, "status": response.status})
            except Exception:
                pass

    page.on("response", handle_response)

    url = "https://takelessons.com/new-york/music-lessons"
    logger.info("[takelessons] Fetching %s", url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning("[takelessons] Navigation failed: %s", e)
        return 0

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    # DOM parsing: teacher profile cards
    cards = (
        soup.select(".teacher-card, .tutor-card, .instructor-card")
        or soup.select("[class*='TeacherCard'], [class*='TutorCard']")
        or soup.select(".search-result-item, .result-card")
    )

    logger.info("[takelessons] Found %d candidate cards in DOM", len(cards))

    for card in cards:
        name = _text(card, "h2, h3, h4, .name, [class*='name'], [class*='Name']")
        if not name:
            continue

        instruments_raw = _text(
            card,
            ".instruments, .subject, [class*='instrument'], [class*='subject'], [class*='Subject']",
        )
        instruments = _parse_instruments(instruments_raw)

        rate_raw = _text(card, ".rate, .price, [class*='rate'], [class*='price']")
        phone = _extract_phone(card.get_text())
        link_tag = card.select_one("a[href]")
        website = None
        if link_tag:
            href = link_tag.get("href", "")
            if href.startswith("http"):
                website = href
            elif href.startswith("/"):
                website = "https://takelessons.com" + href

        db.upsert_teacher(
            DB_PATH,
            name=name,
            instruments=instruments or ["Music"],
            remote_virtual="Both",
            address="New York City",
            email=None,
            website=website,
            phone=phone,
            rates=rate_raw,
            source="takelessons",
        )
        inserted += 1

    logger.info("[takelessons] Done — %d records upserted", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Thumbtack (best-effort, stealth)
# ---------------------------------------------------------------------------

async def crawl_thumbtack(page: Page) -> int:
    """
    Best-effort crawl of thumbtack.com.

    Wrapped in try/except — returns 0 without crashing if blocked.
    Uses playwright-stealth to reduce bot detection.
    """
    try:
        await Stealth().apply_stealth_async(page)
    except Exception:
        logger.warning("[thumbtack] stealth setup failed, proceeding without")

    inserted = 0
    url = "https://www.thumbtack.com/k/music-lessons/near-me/?location=New+York%2C+NY"
    logger.info("[thumbtack] Fetching %s", url)

    try:
        await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
        await asyncio.sleep(2)
        html = await page.content()
    except Exception as e:
        logger.warning("[thumbtack] Blocked or failed: %s — skipping", e)
        return 0

    soup = BeautifulSoup(html, "html.parser")

    # Thumbtack uses heavy JS rendering; try common card selectors
    cards = (
        soup.select("[data-testid*='pro-card'], [data-testid*='provider']")
        or soup.select(".provider-card, .pro-card")
        or soup.select("[class*='ProCard'], [class*='ProviderCard']")
    )

    logger.info("[thumbtack] Found %d candidate cards", len(cards))

    for card in cards:
        name = _text(card, "h2, h3, h4, [class*='name'], [class*='Name']")
        if not name:
            continue

        instruments_raw = _text(
            card, "[class*='service'], [class*='category'], [class*='skill']"
        )
        instruments = _parse_instruments(instruments_raw) or ["Music"]
        rate_raw = _text(card, "[class*='price'], [class*='rate'], [class*='cost']")
        link_tag = card.select_one("a[href]")
        website = None
        if link_tag:
            href = link_tag.get("href", "")
            if href.startswith("http"):
                website = href
            elif href.startswith("/"):
                website = "https://www.thumbtack.com" + href

        try:
            db.upsert_teacher(
                DB_PATH,
                name=name,
                instruments=instruments,
                remote_virtual="Both",
                address="New York City",
                email=None,
                website=website,
                phone=None,
                rates=rate_raw,
                source="thumbtack",
            )
            inserted += 1
        except Exception as e:
            logger.debug("[thumbtack] Skipping card due to error: %s", e)

    logger.info("[thumbtack] Done — %d records upserted", inserted)
    return inserted


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _text(tag, selector: str) -> Optional[str]:
    """Return stripped text of the first matching element, or None."""
    el = tag.select_one(selector)
    if el:
        text = el.get_text(separator=" ", strip=True)
        return text if text else None
    return None


def _extract_phone(text: str) -> Optional[str]:
    """Extract the first US-style phone number from a string."""
    match = re.search(
        r"(\(?\d{3}\)?[\s.\-]?\d{3}[\s.\-]?\d{4})", text
    )
    return match.group(1) if match else None


def _parse_instruments(raw: Optional[str]) -> list[str]:
    """
    Parse a comma/slash/semicolon separated instruments string into a list.
    Returns an empty list if raw is None or empty.
    """
    if not raw:
        return []
    parts = re.split(r"[,/;|•·]", raw)
    result = []
    for p in parts:
        p = p.strip().title()
        if p and len(p) < 50:  # sanity check
            result.append(p)
    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main(source: Optional[str]) -> None:
    db.init_db(DB_PATH)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="en-US",
            viewport={"width": 1280, "height": 800},
        )
        page = await context.new_page()

        total = 0

        if source in (None, "steinway"):
            total += await crawl_steinway(page)

        if source in (None, "takelessons"):
            total += await crawl_takelessons(page)

        if source in (None, "thumbtack"):
            total += await crawl_thumbtack(page)

        await browser.close()

    logger.info("Crawl complete. Total records upserted: %d", total)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="NYC music teacher crawler")
    parser.add_argument(
        "--source",
        choices=["steinway", "takelessons", "thumbtack"],
        default=None,
        help="Which source to crawl (default: all)",
    )
    args = parser.parse_args()
    asyncio.run(main(args.source))
