"""
Per-page entity extraction.
Uses the LLM to extract structured entities from cleaned web page content,
following the dynamically generated schema.
"""

import asyncio
import logging
import config
from llm.client import get_client

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a precise data extractor. Extract all {entity_type_plural} from the web page below.

Attributes to extract for each {entity_type}:
{attribute_list}

Rules:
- Topic: "{query}" — only extract entities clearly related to this topic
- At most 3 entities per response
- Values must be concise (lists: max 3 items; text: max 15 words)
- Set value to null if not found in the text
- Do NOT invent information

You MUST respond with ONLY this exact JSON structure. Every attribute value must be an object with "value", "source_quote", and "confidence" — never a plain string.

Example of correct format:
{{
  "entities": [
    {{
      "attributes": {{
        "name": {{
          "value": "PostgreSQL",
          "source_quote": "PostgreSQL is a powerful open source database",
          "confidence": 0.98
        }},
        "license_type": {{
          "value": "MIT",
          "source_quote": "released under the MIT license",
          "confidence": 0.95
        }},
        "year_founded": {{
          "value": null,
          "source_quote": null,
          "confidence": 0.0
        }}
      }}
    }}
  ]
}}

--- WEB PAGE CONTENT (from: {url}) ---
{content}
--- END CONTENT ---
"""


def _format_attribute_list(attributes: list[dict]) -> str:
    """Format attribute definitions for the prompt."""
    lines = []
    for attr in attributes:
        lines.append(
            f"- {attr['name']} ({attr['type']}): {attr['description']}"
        )
    return "\n".join(lines)


async def extract_from_chunk(
    chunk: str,
    url: str,
    query: str,
    schema: dict,
) -> list[dict]:
    """
    Extract entities from a single text chunk.

    Returns list of entity dicts with attributed values.
    """
    client = get_client()

    attribute_list = _format_attribute_list(schema["attributes"])
    prompt = EXTRACTION_PROMPT.format(
        entity_type=schema["entity_type"],
        entity_type_plural=schema.get("entity_type_plural", schema["entity_type"] + "s"),
        attribute_list=attribute_list,
        query=query,
        url=url,
        content=chunk[:3000],  # Limit input to keep LLM calls fast
    )

    messages = [
        {
            "role": "system",
            "content": "You are a precise data extractor. Return only valid JSON.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        result = await client.chat_json(
            messages,
            timeout=config.LLM_EXTRACT_TIMEOUT,
            max_tokens=config.LLM_EXTRACT_MAX_TOKENS,
            temperature=config.LLM_EXTRACT_TEMPERATURE,
        )
    except Exception as e:
        logger.warning(f"Extraction failed for chunk from {url}: {e}")
        return []

    entities = result.get("entities", [])

    # Normalize and tag each entity with source URL
    normalized = []
    for entity in entities:
        attrs = entity.get("attributes", {})
        # Flatten: pull out value for easy access, keep provenance
        flat_entity = {"_source_url": url, "_attributes": {}}
        for attr_name, attr_data in attrs.items():
            if isinstance(attr_data, dict):
                flat_entity[attr_name] = attr_data.get("value")
                flat_entity["_attributes"][attr_name] = {
                    "value": attr_data.get("value"),
                    "source_quote": attr_data.get("source_quote"),
                    "confidence": attr_data.get("confidence", 0.5),
                    "source_url": url,
                }
            else:
                # Handle case where LLM returns flat values
                flat_entity[attr_name] = attr_data
                flat_entity["_attributes"][attr_name] = {
                    "value": attr_data,
                    "source_quote": None,
                    "confidence": 0.5,
                    "source_url": url,
                }
        normalized.append(flat_entity)

    logger.info(f"Extracted {len(normalized)} entities from {url}")
    return normalized


async def extract_from_page(
    chunks: list[str],
    url: str,
    query: str,
    schema: dict,
    sem: asyncio.Semaphore,
) -> list[dict]:
    """
    Extract entities from all chunks of a single page concurrently,
    gated by a shared semaphore to cap total in-flight LLM calls.
    """
    async def _extract(i: int, chunk: str) -> list[dict]:
        async with sem:
            logger.debug(f"Processing chunk {i+1}/{len(chunks)} from {url}")
            return await extract_from_chunk(chunk, url, query, schema)

    results = await asyncio.gather(*[_extract(i, c) for i, c in enumerate(chunks)])
    all_entities = []
    for entities in results:
        all_entities.extend(entities)
    return all_entities


async def extract_from_all_pages(
    pages: list[dict],
    query: str,
    schema: dict,
) -> list[dict]:
    """
    Extract entities from multiple pages concurrently.

    pages: list of {"url": ..., "chunks": [...]}
    Returns flat list of all extracted entities across all pages.
    A single semaphore (LLM_MAX_CONCURRENT) caps total in-flight LLM
    calls across all pages and chunks combined.
    """
    semaphore = asyncio.Semaphore(config.LLM_MAX_CONCURRENT)

    async def _extract_page(page: dict) -> list[dict]:
        return await extract_from_page(
            page["chunks"], page["url"], query, schema, semaphore
        )

    tasks = [_extract_page(page) for page in pages]
    results = await asyncio.gather(*tasks)

    all_entities = []
    for page_entities in results:
        all_entities.extend(page_entities)

    logger.info(f"Total entities extracted across all pages: {len(all_entities)}")
    return all_entities
