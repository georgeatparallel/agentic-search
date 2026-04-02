"""
Agentic loop: after initial extraction, detect gaps in the results table
and automatically re-search to fill missing information.

This is what makes the system "agentic" — it reasons about its own output
quality and takes corrective action.
"""

import logging

import config
from search.brave import search as brave_search
from scraper.fetcher import fetch_all
from scraper.cleaner import clean_html
from scraper.chunker import chunk_text
from extractor.extract import extract_from_all_pages
from extractor.merge import merge_entities
from extractor.validate import compute_gap_ratio, identify_gaps, generate_gap_queries

logger = logging.getLogger(__name__)


async def run_agentic_loop(
    entities: list[dict],
    query: str,
    schema: dict,
    already_visited_urls: set[str],
    on_status: callable = None,
) -> list[dict]:
    """
    Run the agentic gap-filling loop.

    1. Analyze gaps in current entities
    2. If gap ratio exceeds threshold, generate follow-up queries
    3. Search, scrape, extract from new results
    4. Merge new entities with existing ones
    5. Repeat up to max_iterations

    Args:
        entities: Current merged entity list
        query: Original topic query
        schema: Extraction schema
        already_visited_urls: URLs already scraped (to avoid duplicates)
        on_status: Optional callback for status updates

    Returns:
        Updated entity list with gaps filled
    """
    max_iterations = config.AGENT_MAX_ITERATIONS
    gap_threshold = config.AGENT_GAP_THRESHOLD

    for iteration in range(max_iterations):
        gap_ratio = compute_gap_ratio(entities, schema)

        if gap_ratio <= gap_threshold:
            logger.info(
                f"Gap ratio {gap_ratio:.2%} is below threshold {gap_threshold:.2%}. "
                f"Stopping agentic loop after {iteration} iterations."
            )
            break

        if on_status:
            on_status(f"Gap ratio is {gap_ratio:.0%}. Running follow-up search (iteration {iteration + 1})...")

        logger.info(f"Agentic loop iteration {iteration + 1}: gap ratio = {gap_ratio:.2%}")

        # Identify specific gaps
        gaps = identify_gaps(entities, schema)
        if not gaps:
            break

        # Generate follow-up queries
        follow_up_queries = await generate_gap_queries(gaps, query, schema)
        if not follow_up_queries:
            logger.info("No follow-up queries generated. Stopping.")
            break

        # Search for each follow-up query
        new_search_results = []
        for fq in follow_up_queries:
            results = await brave_search(fq, num_results=5)
            new_search_results.extend(results)

        # Filter out already-visited URLs
        new_urls = []
        for result in new_search_results:
            url = result["url"]
            if url not in already_visited_urls:
                new_urls.append(url)
                already_visited_urls.add(url)

        if not new_urls:
            logger.info("No new URLs to scrape. Stopping.")
            break

        if on_status:
            on_status(f"Scraping {len(new_urls)} new pages...")

        # Fetch and process new pages
        fetched = await fetch_all(new_urls)
        pages = []
        for fetch_result in fetched:
            if fetch_result["html"]:
                cleaned = clean_html(fetch_result["html"], fetch_result["url"])
                if cleaned["text"]:
                    chunks = chunk_text(cleaned["text"])
                    pages.append({"url": fetch_result["url"], "chunks": chunks})

        if not pages:
            logger.info("No new pages yielded content. Stopping.")
            break

        # Extract from new pages
        new_entities = await extract_from_all_pages(pages, query, schema)

        # Merge new entities with existing ones
        all_entities = entities + new_entities
        entities = merge_entities(all_entities, schema)

        logger.info(f"After iteration {iteration + 1}: {len(entities)} entities")

    return entities
