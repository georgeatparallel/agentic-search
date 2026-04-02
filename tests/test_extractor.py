"""
Tests for entity merging and deduplication.
Run with: python -m pytest tests/ -v
"""

from extractor.merge import merge_entities, _similarity


def test_similarity_identical():
    assert _similarity("OpenAI", "OpenAI") == 1.0


def test_similarity_close():
    score = _similarity("OpenAI", "Open AI")
    assert score > 0.75


def test_similarity_different():
    score = _similarity("OpenAI", "Google")
    assert score < 0.5


def test_merge_deduplicates():
    """Entities with similar names should be merged."""
    schema = {
        "attributes": [
            {"name": "name", "display_name": "Name", "description": "", "type": "string"},
            {"name": "founded", "display_name": "Founded", "description": "", "type": "string"},
        ]
    }
    entities = [
        {
            "name": "OpenAI",
            "founded": "2015",
            "_source_url": "https://a.com",
            "_attributes": {
                "name": {"value": "OpenAI", "source_quote": None, "confidence": 0.9, "source_url": "https://a.com"},
                "founded": {"value": "2015", "source_quote": "founded in 2015", "confidence": 0.8, "source_url": "https://a.com"},
            },
        },
        {
            "name": "OpenAI",
            "founded": "2015",
            "_source_url": "https://b.com",
            "_attributes": {
                "name": {"value": "OpenAI", "source_quote": None, "confidence": 0.95, "source_url": "https://b.com"},
                "founded": {"value": "2015", "source_quote": "established 2015", "confidence": 0.9, "source_url": "https://b.com"},
            },
        },
    ]

    merged = merge_entities(entities, schema)
    assert len(merged) == 1
    assert merged[0]["name"] == "OpenAI"
    assert len(merged[0]["_source_urls"]) == 2


def test_merge_keeps_distinct():
    """Entities with different names should stay separate."""
    schema = {
        "attributes": [
            {"name": "name", "display_name": "Name", "description": "", "type": "string"},
        ]
    }
    entities = [
        {"name": "OpenAI", "_source_url": "https://a.com", "_attributes": {}},
        {"name": "Google", "_source_url": "https://b.com", "_attributes": {}},
    ]

    merged = merge_entities(entities, schema)
    assert len(merged) == 2


def test_merge_prefers_higher_confidence():
    """When merging, higher confidence value should win."""
    schema = {
        "attributes": [
            {"name": "name", "display_name": "Name", "description": "", "type": "string"},
            {"name": "ceo", "display_name": "CEO", "description": "", "type": "string"},
        ]
    }
    entities = [
        {
            "name": "Acme",
            "ceo": "Alice",
            "_source_url": "https://a.com",
            "_attributes": {
                "name": {"value": "Acme", "confidence": 0.9, "source_quote": None, "source_url": ""},
                "ceo": {"value": "Alice", "confidence": 0.6, "source_quote": None, "source_url": ""},
            },
        },
        {
            "name": "Acme",
            "ceo": "Bob",
            "_source_url": "https://b.com",
            "_attributes": {
                "name": {"value": "Acme", "confidence": 0.9, "source_quote": None, "source_url": ""},
                "ceo": {"value": "Bob", "confidence": 0.95, "source_quote": "CEO Bob Smith", "source_url": ""},
            },
        },
    ]

    merged = merge_entities(entities, schema)
    assert len(merged) == 1
    assert merged[0]["ceo"] == "Bob"  # Higher confidence
