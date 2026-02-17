"""
Module identifier parsing and validation for NEXUS module system.

Single source of truth for module_id format: "category/platform"
"""
from dataclasses import dataclass
from typing import Optional


@dataclass
class ModuleIdentifier:
    """
    Parsed module identifier.

    Attributes:
        category: Module category (e.g., "weather", "finance")
        platform: Platform identifier (e.g., "openweather", "cibc")
        raw: Original module_id string
    """
    category: str
    platform: str
    raw: str

    def __str__(self) -> str:
        """Return canonical module_id format."""
        return f"{self.category}/{self.platform}"


def parse_module_id(raw: str) -> ModuleIdentifier:
    """
    Parse module_id string into components.

    Expected format: "category/platform" (e.g., "weather/openweather")

    Args:
        raw: Module identifier string

    Returns:
        ModuleIdentifier with parsed components

    Raises:
        ValueError: If module_id format is invalid
    """
    if not raw or not raw.strip():
        raise ValueError("module_id cannot be empty")

    # Handle both "/" and "_" separators (for backwards compatibility)
    if "/" in raw:
        parts = raw.split("/")
    elif "_" in raw:
        # Legacy format: category_platform
        parts = raw.split("_", 1)
    else:
        raise ValueError(
            f"Invalid module_id format: '{raw}'. Expected 'category/platform'"
        )

    if len(parts) != 2:
        raise ValueError(
            f"Invalid module_id format: '{raw}'. Expected exactly 2 parts separated by '/'"
        )

    category = parts[0].strip()
    platform = parts[1].strip()

    if not category:
        raise ValueError(f"module_id category cannot be empty: '{raw}'")

    if not platform:
        raise ValueError(f"module_id platform cannot be empty: '{raw}'")

    return ModuleIdentifier(
        category=category,
        platform=platform,
        raw=raw
    )


def validate_module_id(raw: str) -> bool:
    """
    Validate module_id format without raising exceptions.

    Args:
        raw: Module identifier string to validate

    Returns:
        True if valid, False otherwise
    """
    try:
        parse_module_id(raw)
        return True
    except ValueError:
        return False
