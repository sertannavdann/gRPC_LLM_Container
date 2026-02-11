"""
LIDM: Capability-to-endpoint mapping for multi-instance LLM routing.

Maps task capabilities to the appropriate LLM service tier/endpoint.
"""

import os
import logging
from typing import Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .config_manager import ConfigManager

logger = logging.getLogger(__name__)

# Module-level ConfigManager reference (set at startup)
_config_manager: Optional["ConfigManager"] = None


def set_config_manager(mgr: "ConfigManager") -> None:
    """Wire the ConfigManager for dynamic config lookups."""
    global _config_manager
    _config_manager = mgr
    logger.info("capability_map: ConfigManager wired for dynamic routing")

# Default capability → tier mapping
# The DelegationManager resolves tier → actual endpoint via LLMClientPool
CAPABILITY_MAP: Dict[str, Dict[str, str]] = {
    "coding":        {"tier": "heavy",    "priority": "high"},
    "reasoning":     {"tier": "heavy",    "priority": "high"},
    "analysis":      {"tier": "heavy",    "priority": "medium"},
    "verification":  {"tier": "ultra",    "priority": "high"},
    "deep_research": {"tier": "ultra",    "priority": "high"},
    "finance":       {"tier": "standard", "priority": "medium"},
    "multilingual":  {"tier": "standard", "priority": "medium"},
    "math":          {"tier": "standard", "priority": "medium"},
    "fast_response": {"tier": "standard", "priority": "low"},
    "routing":       {"tier": "standard", "priority": "low"},
    "classification":{"tier": "standard", "priority": "low"},
    "extraction":    {"tier": "standard", "priority": "low"},
    "search":        {"tier": "external", "priority": "medium"},  # Perplexity/web search
}


def get_tier_for_capability(capability: str) -> str:
    """Resolve capability to tier name. Defaults to 'standard'.

    Checks dynamic config first, falls back to static CAPABILITY_MAP.
    """
    if _config_manager is not None:
        tier = _config_manager.get_config().get_tier_for_category(capability)
        if tier is not None:
            return tier
    entry = CAPABILITY_MAP.get(capability, {})
    return entry.get("tier", "standard")


def get_required_tier(capabilities: list) -> str:
    """
    Given a list of required capabilities, determine the highest tier needed.

    Tier hierarchy: ultra > heavy > standard > light > micro
    """
    tier_priority = {"ultra": 0, "heavy": 1, "standard": 2, "light": 3, "micro": 4, "external": 5}
    best_tier = "standard"
    best_rank = tier_priority.get(best_tier, 99)

    for cap in capabilities:
        tier = get_tier_for_capability(cap)
        rank = tier_priority.get(tier, 99)
        if rank < best_rank:
            best_tier = tier
            best_rank = rank

    return best_tier


def get_lidm_endpoints() -> Dict[str, str]:
    """
    Build tier → endpoint mapping.

    Checks dynamic config first, falls back to environment variables.

    Returns dict like:
        {"heavy": "llm_service:50051", "standard": "llm_service_standard:50051", ...}
    """
    if _config_manager is not None:
        dynamic = _config_manager.get_config().get_tier_endpoints()
        if dynamic:
            logger.info(f"LIDM endpoints (dynamic): {dynamic}")
            return dynamic

    endpoints = {}

    heavy = os.getenv("LLM_HEAVY_HOST", "llm_service:50051")
    if heavy:
        endpoints["heavy"] = heavy

    standard = os.getenv("LLM_STANDARD_HOST", "llm_service_standard:50051")
    if standard:
        endpoints["standard"] = standard

    ultra = os.getenv("LLM_ULTRA_HOST", "")
    if ultra:
        endpoints["ultra"] = ultra

    logger.info(f"LIDM endpoints: {endpoints}")
    return endpoints
