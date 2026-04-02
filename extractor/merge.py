"""
Cross-page entity merging and deduplication.
Handles the same entity being mentioned across multiple sources,
resolving conflicts by preferring higher-confidence values.
"""

import logging
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.75  # fuzzy match threshold for entity names


def _normalize_name(name: str) -> str:
    """Normalize an entity name for comparison."""
    if not name:
        return ""
    return name.lower().strip().replace(".", "").replace(",", "").replace("inc", "").replace("llc", "").replace("ltd", "")


def _similarity(a: str, b: str) -> float:
    """Compute string similarity ratio between two names."""
    return SequenceMatcher(None, _normalize_name(a), _normalize_name(b)).ratio()


def _merge_two_entities(existing: dict, new: dict) -> dict:
    """
    Merge a new entity into an existing one.
    For each attribute, keep the value with higher confidence.
    Accumulate source URLs.
    """
    merged = dict(existing)

    # Merge source URLs
    existing_sources = existing.get("_source_urls", [existing.get("_source_url", "")])
    new_source = new.get("_source_url", "")
    if new_source and new_source not in existing_sources:
        existing_sources.append(new_source)
    merged["_source_urls"] = existing_sources

    # Merge attributes
    existing_attrs = existing.get("_attributes", {})
    new_attrs = new.get("_attributes", {})

    merged_attrs = dict(existing_attrs)

    for attr_name, new_attr_data in new_attrs.items():
        if attr_name not in existing_attrs:
            # New attribute not seen before — take it
            merged_attrs[attr_name] = new_attr_data
            merged[attr_name] = new_attr_data.get("value")
        else:
            # Attribute exists — compare confidence
            existing_conf = existing_attrs[attr_name].get("confidence", 0)
            new_conf = new_attr_data.get("confidence", 0)

            existing_val = existing_attrs[attr_name].get("value")
            new_val = new_attr_data.get("value")

            # Prefer non-null value
            if existing_val is None and new_val is not None:
                merged_attrs[attr_name] = new_attr_data
                merged[attr_name] = new_val
            elif new_val is not None and new_conf > existing_conf:
                merged_attrs[attr_name] = new_attr_data
                merged[attr_name] = new_val
            # else keep existing

    merged["_attributes"] = merged_attrs
    return merged


def merge_entities(entities: list[dict], schema: dict) -> list[dict]:
    """
    Merge entities across pages using fuzzy name matching.

    Entities with similar names (above SIMILARITY_THRESHOLD) are merged,
    combining their attributes with conflict resolution.

    Returns deduplicated list of merged entities.
    """
    if not entities:
        return []

    merged = []

    for entity in entities:
        entity_name = entity.get("name", "")
        if not entity_name:
            # Skip entities without a name
            continue

        # Check if this entity matches an existing merged entity
        matched = False
        for i, existing in enumerate(merged):
            existing_name = existing.get("name", "")
            if _similarity(entity_name, existing_name) >= SIMILARITY_THRESHOLD:
                merged[i] = _merge_two_entities(existing, entity)
                matched = True
                logger.debug(f"Merged '{entity_name}' with '{existing_name}'")
                break

        if not matched:
            # Initialize source URLs list
            entity["_source_urls"] = [entity.get("_source_url", "")]
            merged.append(entity)

    logger.info(f"Merged {len(entities)} raw entities into {len(merged)} unique entities")
    return merged
