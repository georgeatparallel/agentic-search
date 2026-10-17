"""Exercise provider selection through the real MCP SDK and HTTP transport."""

import asyncio
import json
from unittest.mock import AsyncMock

import httpx
import pytest

import config
from search import get_search_fn
from search import parallel


@pytest.fixture
def mcp_server(monkeypatch):
    requests = []
    state = {"error": False, "text_only": False, "payload": None, "exception": None, "clients": []}
    original_client = httpx.AsyncClient

    async def handle(request):
        requests.append(request)
        assert str(request.url) == parallel.MCP_URL
        assert request.headers["user-agent"] == parallel.USER_AGENT
        assert "authorization" not in request.headers
        assert "x-api-key" not in request.headers
        if request.method != "POST":
            return httpx.Response(405)
        message = json.loads(request.content)
        method = message["method"]
        if method == "initialize":
            result = {
                "protocolVersion": message["params"]["protocolVersion"],
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "fixture", "version": "1"},
            }
        elif method == "notifications/initialized":
            return httpx.Response(202)
        elif method == "tools/list":
            result = {"tools": [{"name": "web_search", "inputSchema": {"type": "object"}}]}
        elif method == "tools/call":
            if state["exception"]:
                raise state["exception"]
            assert message["params"]["name"] == "web_search"
            arguments = message["params"]["arguments"]
            assert arguments["search_queries"] == [arguments["objective"]]
            assert arguments["session_id"] == parallel.SESSION_ID
            url = "https://example.com/" + arguments["objective"].replace(" ", "-")
            payload = state["payload"] if state["payload"] is not None else {"results": [
                {"title": "Source", "url": url, "excerpts": ["First excerpt", "Second excerpt"]},
                {"title": None, "url": "https://example.org", "excerpts": []},
            ]}
            result = {"content": [{"type": "text", "text": json.dumps(payload)}]}
            if not state["text_only"]:
                result["structuredContent"] = payload
            if state["error"]:
                result = {"isError": True, "content": [{"type": "text", "text": "Search quota exceeded"}]}
        else:
            raise AssertionError(method)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": message["id"], "result": result})

    def client(**kwargs):
        assert kwargs["timeout"] == parallel.SEARCH_TIMEOUT
        instance = original_client(transport=httpx.MockTransport(handle), **kwargs)
        state["clients"].append(instance)
        return instance

    monkeypatch.setattr(parallel.httpx, "AsyncClient", client)
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "parallel")
    monkeypatch.setattr(config, "BRAVE_API_KEY", "")
    return requests, state


@pytest.mark.asyncio
async def test_selected_provider_maps_and_limits_results(mcp_server, monkeypatch):
    requests, state = mcp_server
    monkeypatch.setattr(config, "SEARCH_NUM_RESULTS", 1)
    result = await get_search_fn()("open source databases")
    assert result == [{"title": "Source", "url": "https://example.com/open-source-databases",
                       "snippet": "First excerpt\nSecond excerpt"}]
    state["text_only"] = True
    result = await get_search_fn()("another query", num_results=2)
    assert result[1] == {"title": "", "url": "https://example.org", "snippet": ""}
    assert requests


@pytest.mark.asyncio
async def test_invalid_urls_are_not_sent_to_scraper(mcp_server):
    mcp_server[1]["payload"] = {"results": [
        {"url": "file:///etc/passwd", "excerpts": []},
        {"url": "https://example.org", "excerpts": ["Valid"]},
    ]}
    assert await get_search_fn()("query", 1) == [
        {"title": "", "url": "https://example.org", "snippet": "Valid"}]


@pytest.mark.asyncio
async def test_empty_inputs_do_not_connect(mcp_server):
    for query, count in [(" ", 2), ("query", 0), ("query", -1)]:
        assert await get_search_fn()(query, count) == []
    assert not mcp_server[0]


@pytest.mark.asyncio
async def test_tool_errors_do_not_fall_back(mcp_server):
    mcp_server[1]["error"] = True
    with pytest.raises(RuntimeError, match="Search quota exceeded"):
        await get_search_fn()("query")


@pytest.mark.asyncio
async def test_malformed_result_is_an_error(mcp_server):
    mcp_server[1]["payload"] = {"unexpected": []}
    with pytest.raises(ValueError, match="results list"):
        await get_search_fn()("query")


@pytest.mark.asyncio
@pytest.mark.parametrize("error", [httpx.ConnectError("unavailable"), httpx.ReadTimeout("timed out")])
async def test_transport_error_propagates(mcp_server, error):
    mcp_server[1]["exception"] = error
    with pytest.raises(ExceptionGroup):
        await get_search_fn()("query")


@pytest.mark.asyncio
async def test_deadline_and_cancellation_close_client(mcp_server, monkeypatch):
    original = parallel.ClientSession.call_tool
    entered = asyncio.Event()

    async def blocked(*args, **kwargs):
        entered.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(parallel.ClientSession, "call_tool", blocked)
    monkeypatch.setattr(parallel, "SEARCH_TIMEOUT", 0.1)
    with pytest.raises(TimeoutError):
        await get_search_fn()("deadline")
    assert all(client.is_closed for client in mcp_server[1]["clients"])
    monkeypatch.setattr(parallel, "SEARCH_TIMEOUT", 30)
    entered.clear()
    task = asyncio.create_task(get_search_fn()("cancel"))
    await entered.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert all(client.is_closed for client in mcp_server[1]["clients"])
    monkeypatch.setattr(parallel.ClientSession, "call_tool", original)
    assert await get_search_fn()("after cancellation")


@pytest.mark.parametrize("provider,module", [("brave", "search.brave"),
    ("duckduckgo", "search.fallback"), ("unknown", "search.brave")])
def test_existing_provider_selection(monkeypatch, provider, module):
    monkeypatch.setattr(config, "SEARCH_PROVIDER", provider)
    assert get_search_fn().__module__ == module


@pytest.mark.asyncio
async def test_brave_fallback_is_preserved(monkeypatch):
    from search import brave, fallback
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "brave")
    monkeypatch.setattr(config, "BRAVE_API_KEY", "")
    expected = [{"title": "DDG", "url": "https://example.org", "snippet": "Result"}]
    ddg = AsyncMock(return_value=expected)
    monkeypatch.setattr(fallback, "search", ddg)
    assert get_search_fn() is brave.search
    assert await get_search_fn()("query", 2) == expected
    ddg.assert_awaited_once_with("query", 2)


@pytest.mark.asyncio
async def test_pipeline_passes_configured_count_to_duckduckgo(monkeypatch):
    import pipeline
    from search import fallback

    calls = []

    class FakeDDGS:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def text(self, query, max_results):
            calls.append((query, max_results))
            return [{"title": "Source", "href": f"https://example.com/{i}", "body": "Excerpt"}
                    for i in range(max_results)]

    monkeypatch.setattr(fallback, "DDGS", FakeDDGS)
    monkeypatch.setattr(config, "SEARCH_PROVIDER", "duckduckgo")
    monkeypatch.setattr(config, "SEARCH_NUM_RESULTS", 2)
    monkeypatch.setattr(pipeline, "generate_schema", AsyncMock(return_value={
        "entity_type_plural": "projects", "attributes": []}))
    fetch = AsyncMock(return_value=[])
    monkeypatch.setattr(pipeline, "fetch_all", fetch)
    result = await pipeline.run_pipeline("query", enable_agent=False)
    assert calls == [("query", 2)]
    assert len(result.sources) == 2
    fetch.assert_awaited_once_with(["https://example.com/0", "https://example.com/1"])


@pytest.mark.asyncio
async def test_pipeline_and_agent_consume_selected_provider(mcp_server, monkeypatch):
    import pipeline
    from agent import loop

    schema = {"entity_type_plural": "projects", "attributes": [
        {"name": "name", "display_name": "Name"}]}
    monkeypatch.setattr(pipeline, "generate_schema", AsyncMock(return_value=schema))
    fetched_urls = []

    async def fetch(urls):
        fetched_urls.extend(urls)
        return [{"url": url, "html": "<p>Source content</p>"} for url in urls]

    async def extract(pages, query, schema):
        assert all(page["chunks"] for page in pages)
        return [{"name": page["url"], "_source_url": page["url"], "_attributes": {}}
                for page in pages]

    for module in (pipeline, loop):
        monkeypatch.setattr(module, "fetch_all", fetch)
        monkeypatch.setattr(module, "clean_html", lambda html, url: {
            "title": "Source", "text": "Content about open source database projects. " * 5})
        monkeypatch.setattr(module, "extract_from_all_pages", extract)
    monkeypatch.setattr(loop, "compute_gap_ratio", lambda entities, schema: 1)
    monkeypatch.setattr(loop, "identify_gaps", lambda entities, schema: ["gap"])
    monkeypatch.setattr(loop, "generate_gap_queries", AsyncMock(return_value=["follow up query"]))
    monkeypatch.setattr(config, "AGENT_MAX_ITERATIONS", 1)
    result = await pipeline.run_pipeline("initial query", enable_agent=True)
    assert not result.errors
    assert result.sources[0]["snippet"] == "First excerpt\nSecond excerpt"
    assert "https://example.com/initial-query" in fetched_urls
    assert "https://example.com/follow-up-query" in fetched_urls
    assert len(fetched_urls) == len(set(fetched_urls))  # shared result is not re-fetched
    source_urls = {url for entity in result.entities for url in entity["_source_urls"]}
    assert source_urls == set(fetched_urls)
    calls = [json.loads(r.content) for r in mcp_server[0] if r.method == "POST"]
    queries = [m["params"]["arguments"]["objective"] for m in calls if m["method"] == "tools/call"]
    assert queries == ["initial query", "follow up query"]
