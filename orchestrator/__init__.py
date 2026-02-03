"""
Orchestrator service - Unified agent coordination layer.

Combines agent service, routing, and workflow orchestration into
a single, streamlined service.
"""

from .config import OrchestratorConfig
from .orchestrator_service import OrchestratorService, serve
from .provider_router import (
    ProviderRouter,
    RouterConfig,
    ComplexityLevel,
    ProviderHealth,
    get_router,
    select_provider,
    get_fallback,
)

__all__ = [
    "OrchestratorConfig",
    "OrchestratorService",
    "serve",
    # Provider Router (Week 3)
    "ProviderRouter",
    "RouterConfig",
    "ComplexityLevel",
    "ProviderHealth",
    "get_router",
    "select_provider",
    "get_fallback",
]
