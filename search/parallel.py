"""Anonymous Parallel Search MCP backend using Streamable HTTP."""

import asyncio
import json
import uuid
from urllib.parse import urlsplit

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Implementation

import config

MCP_URL = "https://search.parallel.ai/mcp"
USER_AGENT = "agentic-search/0.1.0 (+https://github.com/NishanthSathish10/agentic-search)"
SEARCH_TIMEOUT = 30
# Reuse one identifier across initial and follow-up searches in this process.
SESSION_ID = uuid.uuid4().hex


async def search(query: str, num_results: int | None = None) -> list[dict]:
    """Return title/url/snippet results, or propagate errors to the caller.

    Parallel is explicitly selected, so failures never switch to another provider.
    The deadline includes MCP initialization, the tool call and connection cleanup.
    """
    limit = config.SEARCH_NUM_RESULTS if num_results is None else num_results
    if not query.strip() or limit <= 0:
        return []

    async with asyncio.timeout(SEARCH_TIMEOUT):
        async with httpx.AsyncClient(
            headers={"User-Agent": USER_AGENT}, timeout=SEARCH_TIMEOUT,
        ) as client:
            async with streamable_http_client(MCP_URL, http_client=client) as (read, write, _):
                async with ClientSession(
                    read, write,
                    client_info=Implementation(name="agentic-search", version="0.1.0"),
                ) as session:
                    await session.initialize()
                    response = await session.call_tool("web_search", {
                        "objective": query,
                        "search_queries": [query],
                        "session_id": SESSION_ID,
                    })

    if response.isError:
        detail = " ".join(block.text for block in response.content if block.type == "text")
        raise RuntimeError(f"Parallel search failed: {detail}")

    data = response.structuredContent
    if data is None:
        # MCP clients may receive the structured result as JSON text content.
        text = next((block.text for block in response.content if block.type == "text"), "")
        data = json.loads(text)
    if not isinstance(data, dict) or not isinstance(data.get("results"), list):
        raise ValueError("Parallel search returned no results list")

    results = []
    for item in data["results"]:
        url = item.get("url", "")
        if urlsplit(url).scheme not in ("http", "https") or not urlsplit(url).netloc:
            continue
        results.append({
            "title": item.get("title") or "",
            "url": url,
            "snippet": "\n".join(item.get("excerpts", [])),
        })
        if len(results) == limit:
            break
    return results
