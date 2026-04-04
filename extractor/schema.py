"""
Dynamic schema generation.
Given a topic query, uses the LLM to determine the entity type and
relevant attributes to extract.
"""

import logging
from llm.client import get_client

logger = logging.getLogger(__name__)

SCHEMA_PROMPT = """You are a data analyst. Given a search topic, determine:
1. What type of entity the user is looking for (e.g., "company", "restaurant", "tool", "person")
2. What attributes (columns) would be most useful in a comparison table

Topic: "{query}"

Respond with ONLY a JSON object in this exact format:
{{
  "entity_type": "the type of entity (singular noun)",
  "entity_type_plural": "plural form",
  "attributes": [
    {{
      "name": "attribute_name_in_snake_case",
      "display_name": "Human Readable Name",
      "description": "What this attribute represents",
      "type": "string | number | list | boolean"
    }}
  ]
}}

Guidelines:
- Include 4-5 attributes that would be most useful and commonly available
- Always include a "name" attribute as the first attribute
- Include attributes that differentiate entities (not ones that would be the same for all)
- Prefer concrete, factual attributes over subjective ones
- Include a "description" or "summary" attribute for a brief overview
"""


async def generate_schema(query: str) -> dict:
    """
    Generate an extraction schema based on the topic query.

    Returns dict with:
      - entity_type: str
      - entity_type_plural: str
      - attributes: list of attribute defs
    """
    client = get_client()

    messages = [
        {"role": "system", "content": "You are a precise data analyst. Return only valid JSON, no extra text."},
        {"role": "user", "content": SCHEMA_PROMPT.format(query=query)},
    ]

    schema = await client.chat_json(messages)

    # Validate the schema has required fields
    if "entity_type" not in schema or "attributes" not in schema:
        raise ValueError(f"Invalid schema generated: {schema}")

    # Ensure 'name' is the first attribute
    attr_names = [a["name"] for a in schema["attributes"]]
    if "name" not in attr_names:
        schema["attributes"].insert(0, {
            "name": "name",
            "display_name": "Name",
            "description": f"Name of the {schema['entity_type']}",
            "type": "string",
        })

    logger.info(
        f"Generated schema for '{query}': entity_type={schema['entity_type']}, "
        f"attributes={[a['name'] for a in schema['attributes']]}"
    )
    return schema
