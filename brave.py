"""
Brave Search API client.
Returns a list of search results with title, URL, and snippet.
"""

import logging
import httpx

import config

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


async def search(query: str, num_results: int | None = None) -> list[dict]:
    """
    Search using Brave Search API.

    Returns list of dicts: [{"title": ..., "url": ..., "snippet": ...}, ...]
    """
    num_results = num_results or config.SEARCH_NUM_RESULTS

    if not config.BRAVE_API_KEY:
        logger.warning("No BRAVE_API_KEY set, falling back to DuckDuckGo")
        from search.fallback import search as ddg_search
        return await ddg_search(query, num_results)

    headers = {
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
        "X-Subscription-Token": config.BRAVE_API_KEY,
    }
    params = {
        "q": query,
        "count": num_results,
        "text_decorations": False,
        "search_lang": "en",
    }

    async with httpx.AsyncClient(timeout=15) as client:
        try:
            resp = await client.get(BRAVE_SEARCH_URL, headers=headers, params=params)
            resp.raise_for_status()
            data = resp.json()
        except httpx.HTTPStatusError as e:
            logger.error(f"Brave Search API error: {e.response.status_code}")
            from search.fallback import search as ddg_search
            return await ddg_search(query, num_results)
        except Exception as e:
            logger.error(f"Brave Search request failed: {e}")
            from search.fallback import search as ddg_search
            return await ddg_search(query, num_results)

    results = []
    web_results = data.get("web", {}).get("results", [])
    for item in web_results[:num_results]:
        results.append({
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "snippet": item.get("description", ""),
        })

    logger.info(f"Brave search for '{query}' returned {len(results)} results")
    return results
