"""
Async HTTP page fetcher using httpx.
Fetches multiple pages concurrently with rate limiting and error handling.
"""

import asyncio
import logging
import httpx

import config

logger = logging.getLogger(__name__)


async def fetch_one(client: httpx.AsyncClient, url: str) -> dict:
    """
    Fetch a single URL. Returns dict with url, html, status, and error fields.
    """
    try:
        resp = await client.get(
            url,
            follow_redirects=True,
            headers={"User-Agent": config.USER_AGENT},
        )
        resp.raise_for_status()

        # Skip non-HTML responses (PDFs, images, etc.)
        content_type = resp.headers.get("content-type", "")
        if "text/html" not in content_type and "application/xhtml" not in content_type:
            logger.info(f"Skipping non-HTML content at {url}: {content_type}")
            return {"url": url, "html": None, "status": resp.status_code, "error": "non-html"}

        return {
            "url": url,
            "html": resp.text,
            "status": resp.status_code,
            "error": None,
        }

    except httpx.HTTPStatusError as e:
        logger.warning(f"HTTP {e.response.status_code} for {url}")
        return {"url": url, "html": None, "status": e.response.status_code, "error": str(e)}
    except httpx.TimeoutException:
        logger.warning(f"Timeout fetching {url}")
        return {"url": url, "html": None, "status": None, "error": "timeout"}
    except Exception as e:
        logger.warning(f"Error fetching {url}: {e}")
        return {"url": url, "html": None, "status": None, "error": str(e)}


async def fetch_all(urls: list[str]) -> list[dict]:
    """
    Fetch multiple URLs concurrently, respecting max concurrency.

    Returns list of dicts: [{"url": ..., "html": ..., "status": ..., "error": ...}, ...]
    """
    semaphore = asyncio.Semaphore(config.SCRAPE_MAX_CONCURRENT)

    async def _limited_fetch(client: httpx.AsyncClient, url: str) -> dict:
        async with semaphore:
            return await fetch_one(client, url)

    async with httpx.AsyncClient(timeout=config.SCRAPE_TIMEOUT) as client:
        tasks = [_limited_fetch(client, url) for url in urls]
        results = await asyncio.gather(*tasks)

    successful = sum(1 for r in results if r["html"] is not None)
    logger.info(f"Fetched {successful}/{len(urls)} pages successfully")
    return results
