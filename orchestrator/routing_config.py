"""
Pydantic schemas for dynamic routing configuration.

Defines type-safe, validated config for LIDM routing:
- Per-category model/provider/tier assignment
- Tier endpoint configuration
- Performance constraint thresholds
"""

from pydantic import BaseModel, Field
from typing import Dict, Optional


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
            if tier_cfg.enabled and tier_cfg.endpoint:
                endpoints[name] = tier_cfg.endpoint
        return endpoints
