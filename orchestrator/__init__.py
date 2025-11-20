"""
Orchestrator service - Unified agent coordination layer.

Combines agent service, routing, and workflow orchestration into
a single, streamlined service.
"""

from .config import OrchestratorConfig
from .orchestrator_service import OrchestratorService, serve

__all__ = [
    "OrchestratorConfig",
    "OrchestratorService",
    "serve",
]
