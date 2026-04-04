"""
Pipeline orchestrator.
Chains together all stages: search → scrape → clean → chunk → extract → merge → validate → agent loop.
"""

import logging
import time
from dataclasses import dataclass, field

from search.brave import search as brave_search
from scraper.fetcher import fetch_all
from scraper.cleaner import clean_html
from scraper.chunker import chunk_text
from extractor.schema import generate_schema
from extractor.extract import extract_from_all_pages
from extractor.merge import merge_entities
from extractor.validate import compute_gap_ratio
from agent.loop import run_agentic_loop

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Container for pipeline output."""
    query: str = ""
    schema: dict = field(default_factory=dict)
    entities: list[dict] = field(default_factory=list)
    sources: list[dict] = field(default_factory=list)
    gap_ratio: float = 1.0
    timing: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)
    status_log: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        """Serialize to a JSON-friendly dictionary."""
        # Build clean entity rows for the table
        attr_names = [a["name"] for a in self.schema.get("attributes", [])]
        table_rows = []
        for entity in self.entities:
            row = {}
            sources = {}
            entity_attrs = entity.get("_attributes", {})
            for attr_name in attr_names:
                val = entity.get(attr_name)
                # Flatten plain dicts to a comma-separated string so the frontend never sees [object Object]
                if isinstance(val, dict):
                    val = ", ".join(str(v) for v in val.values() if v is not None) or None
                row[attr_name] = val
                # Exact key match first, then fall back to any _attributes key
                # that is a substring of or contains the schema attribute name.
                # This handles LLM aliases like company_name→name, found_date→founded_year.
                attr_meta = entity_attrs.get(attr_name)
                if attr_meta is None:
                    for key, meta in entity_attrs.items():
                        if attr_name in key or key in attr_name:
                            attr_meta = meta
                            break
                attr_meta = attr_meta or {}
                sources[attr_name] = {
                    "source_quote": attr_meta.get("source_quote"),
                    "source_url": attr_meta.get("source_url"),
                    "confidence": attr_meta.get("confidence"),
                }
            row["_sources"] = sources
            row["_source_urls"] = entity.get("_source_urls", [])
            table_rows.append(row)

        return {
            "query": self.query,
            "schema": self.schema,
            "columns": [
                {"name": a["name"], "display_name": a["display_name"]}
                for a in self.schema.get("attributes", [])
            ],
            "entities": table_rows,
            "entity_count": len(table_rows),
            "gap_ratio": self.gap_ratio,
            "sources_used": self.sources,
            "timing": self.timing,
            "errors": self.errors,
        }


async def run_pipeline(
    query: str,
    enable_agent: bool = True,
    on_status: callable = None,
) -> PipelineResult:
    """
    Execute the full agentic search pipeline.

    Args:
        query: Topic search query
        enable_agent: Whether to run the agentic gap-filling loop
        on_status: Optional callback for real-time status updates

    Returns:
        PipelineResult with all entities and metadata
    """
    result = PipelineResult(query=query)
    overall_start = time.time()

    def status(msg: str):
        result.status_log.append(msg)
        logger.info(msg)
        if on_status:
            on_status(msg)

    # --- Step 1: Generate extraction schema ---
    status("Analyzing query and generating extraction schema...")
    t0 = time.time()
    try:
        schema = await generate_schema(query)
        result.schema = schema
    except Exception as e:
        result.errors.append(f"Schema generation failed: {e}")
        logger.error(f"Schema generation failed: {e}")
        return result
    result.timing["schema_generation"] = round(time.time() - t0, 2)
    status(f"Schema ready: looking for {schema['entity_type_plural']} with {len(schema['attributes'])} attributes")

    # --- Step 2: Search ---
    status("Searching the web...")
    t0 = time.time()
    try:
        search_results = await brave_search(query)
        result.sources = search_results
    except Exception as e:
        result.errors.append(f"Search failed: {e}")
        logger.error(f"Search failed: {e}")
        return result
    result.timing["search"] = round(time.time() - t0, 2)
    status(f"Found {len(search_results)} search results")

    if not search_results:
        result.errors.append("No search results found")
        return result

    # --- Step 3: Fetch pages ---
    status("Fetching web pages...")
    t0 = time.time()
    urls = [r["url"] for r in search_results]
    visited_urls = set(urls)
    fetched_pages = await fetch_all(urls)
    result.timing["fetching"] = round(time.time() - t0, 2)

    successful_fetches = [p for p in fetched_pages if p["html"]]
    status(f"Successfully fetched {len(successful_fetches)}/{len(urls)} pages")

    if not successful_fetches:
        result.errors.append("Could not fetch any pages")
        return result

    # --- Step 4: Clean and chunk ---
    status("Cleaning and chunking content...")
    t0 = time.time()
    pages_with_chunks = []
    for page in successful_fetches:
        cleaned = clean_html(page["html"], page["url"])
        if cleaned["text"] and len(cleaned["text"]) > 50:
            chunks = chunk_text(cleaned["text"])
            pages_with_chunks.append({
                "url": page["url"],
                "chunks": chunks,
                "title": cleaned["title"],
            })

    result.timing["cleaning"] = round(time.time() - t0, 2)
    status(f"Prepared {len(pages_with_chunks)} pages ({sum(len(p['chunks']) for p in pages_with_chunks)} chunks)")

    if not pages_with_chunks:
        result.errors.append("No usable content extracted from pages")
        return result

    # --- Step 5: Extract entities ---
    status("Extracting entities with LLM (this may take a moment with local models)...")
    t0 = time.time()
    raw_entities = await extract_from_all_pages(pages_with_chunks, query, schema)
    result.timing["extraction"] = round(time.time() - t0, 2)
    status(f"Extracted {len(raw_entities)} raw entities")

    # --- Step 6: Merge and deduplicate ---
    status("Merging and deduplicating entities...")
    t0 = time.time()
    merged_entities = merge_entities(raw_entities, schema)
    result.timing["merging"] = round(time.time() - t0, 2)
    status(f"Merged into {len(merged_entities)} unique entities")

    # --- Step 7: Agentic gap-filling loop ---
    if enable_agent and merged_entities:
        status("Checking for information gaps...")
        t0 = time.time()
        merged_entities = await run_agentic_loop(
            entities=merged_entities,
            query=query,
            schema=schema,
            already_visited_urls=visited_urls,
            on_status=status,
        )
        result.timing["agent_loop"] = round(time.time() - t0, 2)

    result.entities = merged_entities
    result.gap_ratio = compute_gap_ratio(merged_entities, schema)

    result.timing["total"] = round(time.time() - overall_start, 2)
    status(f"Done! Found {len(merged_entities)} entities in {result.timing['total']}s")

    return result
