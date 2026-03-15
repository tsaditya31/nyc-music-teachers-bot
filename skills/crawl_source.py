"""Skill: Fetch page HTML via Playwright or httpx."""

import logging
import re
from brain.orchestrator import register_skill

logger = logging.getLogger(__name__)


def _clean_html(html: str, max_bytes: int = 80_000) -> str:
    """Strip scripts, styles, nav, header, footer. Truncate to max_bytes."""
    # Remove script and style tags with content
    html = re.sub(r"<script[^>]*>[\s\S]*?</script>", "", html, flags=re.IGNORECASE)
    html = re.sub(r"<style[^>]*>[\s\S]*?</style>", "", html, flags=re.IGNORECASE)
    # Remove nav, header, footer tags
    for tag in ["nav", "header", "footer", "noscript", "iframe"]:
        html = re.sub(rf"<{tag}[^>]*>[\s\S]*?</{tag}>", "", html, flags=re.IGNORECASE)
    # Collapse whitespace
    html = re.sub(r"\s{2,}", " ", html)
    # Truncate
    if len(html) > max_bytes:
        html = html[:max_bytes] + "\n<!-- TRUNCATED -->"
    return html


@register_skill({
    "name": "crawl_source",
    "description": "Fetch a web page and return cleaned HTML content ready for extraction. Uses Playwright for JavaScript-heavy pages.",
    "input_schema": {
        "type": "object",
        "properties": {
            "url": {
                "type": "string",
                "description": "The URL to fetch",
            },
            "use_browser": {
                "type": "boolean",
                "description": "Use Playwright browser (for JS-rendered pages). Default: true",
            },
        },
        "required": ["url"],
    },
})
async def crawl_source_skill(url: str, use_browser: bool = True) -> str:
    if use_browser:
        return await _fetch_with_playwright(url)
    else:
        return await _fetch_with_httpx(url)


async def _fetch_with_httpx(url: str) -> str:
    import httpx
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            resp = await client.get(url, headers={"User-Agent": "Mozilla/5.0 NYCKidsBot/1.0"})
            resp.raise_for_status()
            return _clean_html(resp.text)
    except Exception as e:
        return f"Error fetching {url}: {e}"


async def _fetch_with_playwright(url: str) -> str:
    try:
        from playwright.async_api import async_playwright
    except ImportError:
        logger.warning("Playwright not available, falling back to httpx")
        return await _fetch_with_httpx(url)

    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                locale="en-US",
            )
            page = await context.new_page()
            await page.goto(url, wait_until="networkidle", timeout=30000)
            html = await page.content()
            await browser.close()
            return _clean_html(html)
    except Exception as e:
        logger.exception(f"Playwright failed for {url}, falling back to httpx")
        return await _fetch_with_httpx(url)
