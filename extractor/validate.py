"""
Validation and gap detection.
Analyzes the merged entity table to find missing values and
generates follow-up search queries to fill gaps.
"""

import logging
from llm.client import get_client

logger = logging.getLogger(__name__)


def compute_gap_ratio(entities: list[dict], schema: dict) -> float:
    """
    Compute the fraction of cells that are null/empty in the entity table.
    Returns a float between 0.0 (no gaps) and 1.0 (all gaps).
    """
    if not entities or not schema.get("attributes"):
        return 1.0

    attr_names = [a["name"] for a in schema["attributes"]]
    total_cells = len(entities) * len(attr_names)
    if total_cells == 0:
        return 1.0

    empty_cells = 0
    for entity in entities:
        for attr_name in attr_names:
            val = entity.get(attr_name)
            if val is None or val == "" or val == "null":
                empty_cells += 1

    ratio = empty_cells / total_cells
    logger.info(f"Gap ratio: {empty_cells}/{total_cells} = {ratio:.2%}")
    return ratio


def identify_gaps(entities: list[dict], schema: dict) -> list[dict]:
    """
    Identify specific gaps in the entity table.

    Returns list of dicts: [{"entity_name": ..., "missing_attributes": [...]}, ...]
    """
    attr_names = [a["name"] for a in schema["attributes"]]
    gaps = []

    for entity in entities:
        entity_name = entity.get("name", "Unknown")
        missing = []
        for attr_name in attr_names:
            val = entity.get(attr_name)
            if val is None or val == "" or val == "null":
                missing.append(attr_name)
        if missing:
            gaps.append({
                "entity_name": entity_name,
                "missing_attributes": missing,
            })

    return gaps


async def generate_gap_queries(
    gaps: list[dict], query: str, schema: dict
) -> list[str]:
    """
    Use the LLM to generate follow-up search queries that could fill gaps.

    Returns list of search query strings.
    """
    if not gaps:
        return []

    # Only generate queries for the most significant gaps
    # (entities missing the most attributes)
    gaps_sorted = sorted(gaps, key=lambda g: len(g["missing_attributes"]), reverse=True)
    top_gaps = gaps_sorted[:5]  # Max 5 follow-up queries

    client = get_client()

    gap_descriptions = []
    for gap in top_gaps:
        gap_descriptions.append(
            f"- {gap['entity_name']}: missing {', '.join(gap['missing_attributes'])}"
        )

    prompt = f"""Given the original search topic "{query}", I found some {schema['entity_type_plural']} but am missing information.

Gaps:
{chr(10).join(gap_descriptions)}

Generate 1-3 targeted search queries that would help fill these gaps.
Return ONLY a JSON object: {{"queries": ["query1", "query2"]}}

Guidelines:
- Make queries specific enough to find the missing information
- Include the entity name in queries when looking for specific entity attributes
- Keep queries short (3-8 words)
"""

    messages = [
        {"role": "system", "content": "You generate search queries. Return only valid JSON."},
        {"role": "user", "content": prompt},
    ]

    try:
        result = await client.chat_json(messages)
        queries = result.get("queries", [])
        logger.info(f"Generated {len(queries)} follow-up queries: {queries}")
        return queries
    except Exception as e:
        logger.warning(f"Failed to generate gap queries: {e}")
        return []
