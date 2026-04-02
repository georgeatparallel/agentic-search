"""
Per-page entity extraction.
Uses the LLM to extract structured entities from cleaned web page content,
following the dynamically generated schema.
"""

import asyncio
import logging
from llm.client import get_client

logger = logging.getLogger(__name__)

EXTRACTION_PROMPT = """You are a precise data extractor. Extract all {entity_type_plural} mentioned in the following web page content.

For each {entity_type} found, extract these attributes:
{attribute_list}

IMPORTANT RULES:
- Only extract entities that are clearly {entity_type_plural} related to the topic: "{query}"
- For each attribute value, include the exact supporting quote from the text
- If an attribute is not mentioned for an entity, set its value to null
- Assign a confidence score (0.0 to 1.0) for each attribute based on how explicit the information is
- Do NOT invent or hallucinate information not present in the text

Respond with ONLY a JSON object in this format:
{{
  "entities": [
    {{
      "attributes": {{
        "attribute_name": {{
          "value": "the extracted value or null",
          "source_quote": "exact quote from text supporting this value, or null",
          "confidence": 0.95
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
        content=chunk[:6000],  # Safety limit to avoid token overflow
    )

    messages = [
        {
            "role": "system",
            "content": "You are a precise data extractor. Return only valid JSON.",
        },
        {"role": "user", "content": prompt},
    ]

    try:
        result = await client.chat_json(messages, timeout=180.0)
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
) -> list[dict]:
    """
    Extract entities from all chunks of a single page.
    Processes chunks sequentially to avoid overwhelming the local LLM.
    """
    all_entities = []
    for i, chunk in enumerate(chunks):
        logger.debug(f"Processing chunk {i+1}/{len(chunks)} from {url}")
        entities = await extract_from_chunk(chunk, url, query, schema)
        all_entities.extend(entities)
    return all_entities


async def extract_from_all_pages(
    pages: list[dict],
    query: str,
    schema: dict,
    max_concurrent: int = 3,
) -> list[dict]:
    """
    Extract entities from multiple pages.

    pages: list of {"url": ..., "chunks": [...]}
    Returns flat list of all extracted entities across all pages.
    """
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _extract_page(page: dict) -> list[dict]:
        async with semaphore:
            return await extract_from_page(
                page["chunks"], page["url"], query, schema
            )

    tasks = [_extract_page(page) for page in pages]
    results = await asyncio.gather(*tasks)

    all_entities = []
    for page_entities in results:
        all_entities.extend(page_entities)

    logger.info(f"Total entities extracted across all pages: {len(all_entities)}")
    return all_entities
