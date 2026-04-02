"""
Tests for scraper functionality (cleaner, chunker).
Run with: python -m pytest tests/ -v
"""

from scraper.cleaner import clean_html
from scraper.chunker import chunk_text, estimate_tokens


def test_clean_html_extracts_content():
    """Test that cleaner extracts main content from HTML."""
    html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <nav>Navigation stuff</nav>
        <main>
            <h1>Main Article Title</h1>
            <p>This is the main content of the article. It has important information
            that should be extracted by the cleaner.</p>
            <p>Another paragraph with more details about the topic at hand.</p>
        </main>
        <footer>Footer stuff</footer>
    </body>
    </html>
    """
    result = clean_html(html, url="https://example.com")
    assert result["text"] != ""
    assert "main content" in result["text"].lower() or "article" in result["text"].lower()


def test_clean_html_empty_input():
    """Test that empty HTML returns empty result."""
    result = clean_html("", url="")
    assert result["text"] == ""


def test_chunk_text_short_text():
    """Short text should return a single chunk."""
    text = "This is a short text."
    chunks = chunk_text(text)
    assert len(chunks) == 1
    assert chunks[0] == text


def test_chunk_text_long_text():
    """Long text should be split into multiple chunks."""
    # Generate text that's definitely longer than the default max tokens
    text = ("This is a sentence with several words. " * 500)
    chunks = chunk_text(text, max_tokens=200, overlap_tokens=50)
    assert len(chunks) > 1


def test_estimate_tokens():
    """Token estimation should be roughly correct."""
    text = "word " * 100  # 100 words
    tokens = estimate_tokens(text)
    # Should be in the right ballpark (100 words ≈ 133 tokens)
    assert 80 < tokens < 200


def test_chunk_overlap():
    """Chunks should have overlapping content."""
    text = " ".join(f"word{i}" for i in range(500))
    chunks = chunk_text(text, max_tokens=100, overlap_tokens=20)
    if len(chunks) >= 2:
        # Last words of chunk 0 should appear in chunk 1
        words_end_0 = set(chunks[0].split()[-15:])
        words_start_1 = set(chunks[1].split()[:30])
        overlap = words_end_0 & words_start_1
        assert len(overlap) > 0, "Chunks should have overlapping content"
