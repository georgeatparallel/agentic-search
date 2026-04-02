"""
DuckDuckGo fallback search using the duckduckgo-search library.
No API key required. Used when Brave API key is not set or Brave fails.
"""

import logging
from duckduckgo_search import DDGS

logger = logging.getLogger(__name__)


async def search(query: str, num_results: int = 10) -> list[dict]:
    """
    Search using DuckDuckGo (no API key needed).
    Runs synchronously under the hood but wrapped for async interface consistency.

    Returns list of dicts: [{"title": ..., "url": ..., "snippet": ...}, ...]
    """
    results = []
    try:
        with DDGS() as ddgs:
            for r in ddgs.text(query, max_results=num_results):
                results.append({
                    "title": r.get("title", ""),
                    "url": r.get("href", ""),
                    "snippet": r.get("body", ""),
                })
    except Exception as e:
        logger.error(f"DuckDuckGo search failed: {e}")
        return []

    logger.info(f"DDG search for '{query}' returned {len(results)} results")
    return results
