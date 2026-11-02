"""
Pydantic schemas for dynamic routing configuration.

Defines type-safe, validated config for LIDM routing:
- Per-category model/provider/tier assignment
- Tier endpoint configuration
- Performance constraint thresholds
"""

import os
import re

from pydantic import BaseModel, Field
from typing import Dict, Optional

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def expand_env(value: str) -> str:
    """
    Expand ``${VAR}`` and ``${VAR:-default}`` references, compose-style.

    Used for tier endpoints so one routing_config.json serves both the Docker
    CPU tiers (``llm_service:50051``) and host-native Metal tiers
    (``host.docker.internal:50051``) chosen by LLM_HEAVY_HOST / LLM_STANDARD_HOST.
    An unset or empty variable falls back to the default.
    """
    def _sub(match: "re.Match[str]") -> str:
        current = os.environ.get(match.group(1))
        if current:
            return current
        return match.group(2) or ""

    return _ENV_REF.sub(_sub, value)


class CategoryRouting(BaseModel):
    """Routing config for a single capability category."""
    tier: str = "standard"
    provider: Optional[str] = None
    model: Optional[str] = None
    priority: str = "medium"
    max_latency_ms: Optional[int] = None


class TierConfig(BaseModel):
    """Configuration for a single LLM tier endpoint."""
    endpoint: str = ""
    max_concurrent_requests: int = 10
    priority: int = 1
    enabled: bool = True


class PerformanceConstraints(BaseModel):
    """Configurable thresholds for delegation decisions."""
    complexity_threshold_direct: float = Field(
        default=0.5,
        description="Queries below this complexity are routed directly (no decomposition).",
    )
    self_consistency_threshold: float = Field(
        default=0.6,
        description="Self-consistency score >= this is considered verified.",
    )
    delegation_latency_threshold_ms: int = Field(
        default=5000,
        description="Maximum acceptable latency for delegation path.",
    )
    max_sub_tasks: int = Field(
        default=5,
        description="Cap on sub-tasks from LLM decomposition.",
    )


class RoutingConfig(BaseModel):
    """
    Top-level routing configuration.

    Loaded from config/routing_config.json, hot-reloadable via admin API.
    """
    version: str = "1.0"
    categories: Dict[str, CategoryRouting] = {}
    tiers: Dict[str, TierConfig] = {}
    performance: PerformanceConstraints = PerformanceConstraints()

    def get_tier_for_category(self, category: str) -> Optional[str]:
        """Resolve category to tier name, or None if not configured."""
        entry = self.categories.get(category)
        if entry:
            return entry.tier
        return None

    def get_capability_map(self) -> Dict[str, Dict[str, str]]:
        """Return legacy CAPABILITY_MAP-format dict for backward compat."""
        result = {}
        for name, cat in self.categories.items():
            result[name] = {"tier": cat.tier, "priority": cat.priority}
        return result

    def get_tier_endpoints(self) -> Dict[str, str]:
        """Return tier→'host:port' mapping from enabled tiers."""
        endpoints = {}
        for name, tier_cfg in self.tiers.items():
            # Expand at read time so saving the config keeps the ${...} template.
            endpoint = expand_env(tier_cfg.endpoint) if tier_cfg.endpoint else ""
            if tier_cfg.enabled and endpoint:
                endpoints[name] = endpoint
        return endpoints
