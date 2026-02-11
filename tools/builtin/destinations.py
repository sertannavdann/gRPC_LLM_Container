"""
Centralized destination alias resolution.
Maps user-friendly location names to saved destination keys.
"""
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Canonical destination aliases
DESTINATION_ALIASES: Dict[str, List[str]] = {
    "office": ["work", "the office", "my office", "job", "workplace", "company"],
    "home": ["house", "my place", "apartment", "my home", "residence"],
    "gym": ["fitness", "workout", "the gym", "fitness center", "health club"],
    "school": ["university", "college", "campus", "class"],
    "airport": ["the airport", "terminal", "flights"],
}


def normalize_destination(query: str) -> str:
    """
    Normalize a destination query string.

    Args:
        query: User's destination input (e.g., "the office", "Work")

    Returns:
        Normalized lowercase string
    """
    return query.lower().strip()


def resolve_alias(query: str) -> Optional[str]:
    """
    Resolve a destination alias to its canonical key.

    Args:
        query: User's destination string (e.g., "the office", "work")

    Returns:
        Canonical destination key (e.g., "office") or None if no alias match
    """
    normalized = normalize_destination(query)

    # Direct match on canonical key
    if normalized in DESTINATION_ALIASES:
        return normalized

    # Check aliases
    for canonical, aliases in DESTINATION_ALIASES.items():
        if normalized in [a.lower() for a in aliases]:
            return canonical
        # Partial match for phrases like "the office" -> "office"
        if normalized == f"the {canonical}":
            return canonical

    return None


def resolve_destination(
    query: str,
    saved_destinations: Dict[str, Any],
    default_key: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """
    Resolve a destination query against saved destinations.

    First tries alias resolution, then direct key match, then fuzzy search.

    Args:
        query: User's destination string (e.g., "the office", "work")
        saved_destinations: Dict of saved destination configs with structure:
            {"office": {"address": "...", "coordinates": {...}}, ...}
        default_key: Optional default destination key if query is empty

    Returns:
        Matched destination dict with added 'key' field, or None if not found

    Example:
        >>> saved = {"office": {"address": "123 Main St"}}
        >>> resolve_destination("work", saved)
        {"key": "office", "address": "123 Main St"}
    """
    if not query and default_key:
        query = default_key

    if not query:
        return None

    normalized = normalize_destination(query)

    # Strategy 1: Alias resolution
    canonical = resolve_alias(query)
    if canonical and canonical in saved_destinations:
        result = saved_destinations[canonical].copy()
        result['key'] = canonical
        return result

    # Strategy 2: Direct key match
    if normalized in saved_destinations:
        result = saved_destinations[normalized].copy()
        result['key'] = normalized
        return result

    # Strategy 3: Partial key match (e.g., "off" matches "office")
    for key in saved_destinations:
        if key.startswith(normalized) or normalized.startswith(key):
            result = saved_destinations[key].copy()
            result['key'] = key
            logger.debug(f"Partial match: '{query}' -> '{key}'")
            return result

    # Strategy 4: Search in destination names/addresses
    for key, dest in saved_destinations.items():
        if isinstance(dest, dict):
            name = dest.get('name', '').lower()
            address = dest.get('address', '').lower()
            if normalized in name or normalized in address:
                result = dest.copy()
                result['key'] = key
                return result

    logger.debug(f"No destination match for: '{query}'")
    return None


def get_available_destinations(saved_destinations: Dict[str, Any]) -> List[str]:
    """
    Get list of available destination keys for error messages.

    Args:
        saved_destinations: Dict of saved destinations

    Returns:
        List of destination keys
    """
    return list(saved_destinations.keys())
