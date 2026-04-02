"""
Basic tests for search functionality.
Run with: python -m pytest tests/ -v
"""

import asyncio
import pytest


def test_ddg_search_returns_results():
    """Test that DuckDuckGo fallback returns results."""
    from search.fallback import search

    results = asyncio.run(search("python programming language", num_results=3))
    assert isinstance(results, list)
    assert len(results) > 0
    assert "title" in results[0]
    assert "url" in results[0]
    assert "snippet" in results[0]


def test_ddg_search_handles_empty_query():
    """Test that empty query doesn't crash."""
    from search.fallback import search

    results = asyncio.run(search("", num_results=3))
    assert isinstance(results, list)
