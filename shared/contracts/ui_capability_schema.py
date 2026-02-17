"""
Pydantic models for capability contract between backend and UI.

This is the **query model** (CQRS pattern) — a read-optimized projection of system state.
The command side (module install, credential store, provider config) remains independent.

Academic anchor: Event-Driven Microservice Orchestration Principles §4.2
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class FeatureStatus(str, Enum):
    """Feature health status for monitoring dashboard."""

    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNAVAILABLE = "unavailable"
    UNKNOWN = "unknown"


class ToolCapability(BaseModel):
    """Orchestrator tool capability (builtin or custom)."""

    model_config = ConfigDict(from_attributes=True)

    name: str = Field(..., description="Tool identifier (e.g., 'weather', 'calendar')")
    description: str = Field(..., description="Human-readable tool description")
    registered: bool = Field(..., description="Whether tool is currently registered")
    category: str = Field(..., description="Tool category: 'builtin' or 'custom'")


class ModuleCapability(BaseModel):
    """Module capability from registry."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Module identifier (category-platform)")
    name: str = Field(..., description="Human-readable module name")
    category: str = Field(..., description="Module category (weather, calendar, etc.)")
    platform: str = Field(..., description="Platform name (openweather, google, etc.)")
    status: str = Field(
        ..., description="Module status: 'installed', 'draft', or 'disabled'"
    )
    version: Optional[int] = Field(default=None, description="Current version number")
    has_tests: bool = Field(default=False, description="Whether module has test suite")


class ProviderCapability(BaseModel):
    """LLM provider capability from provider registry."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Provider identifier")
    name: str = Field(..., description="Provider display name")
    tier: str = Field(
        ...,
        description="Provider tier: 'standard' (0.5B), 'heavy' (14B), or 'ultra' (70B+)",
    )
    locked: bool = Field(
        ...,
        description="Whether provider is locked due to missing credentials or configuration",
    )
    connection_tested: bool = Field(
        default=False, description="Whether connection test has been run"
    )
    last_test_ok: Optional[bool] = Field(
        default=None, description="Result of last connection test (None if not tested)"
    )


class AdapterCapability(BaseModel):
    """Adapter capability from adapter registry (NEW for Phase 6)."""

    model_config = ConfigDict(from_attributes=True)

    id: str = Field(..., description="Adapter identifier (category-platform)")
    name: str = Field(..., description="Human-readable adapter name")
    category: str = Field(..., description="Adapter category (weather, calendar, etc.)")
    locked: bool = Field(
        ...,
        description="Whether adapter is locked due to missing credentials or configuration",
    )
    missing_fields: list[str] = Field(
        default_factory=list, description="List of missing credential fields"
    )
    last_data_timestamp: Optional[str] = Field(
        default=None, description="ISO 8601 timestamp of last successful data fetch"
    )
    connection_tested: bool = Field(
        default=False, description="Whether connection test has been run"
    )
    last_test_ok: Optional[bool] = Field(
        default=None, description="Result of last connection test (None if not tested)"
    )


class FeatureHealth(BaseModel):
    """Per-feature health status for monitoring."""

    model_config = ConfigDict(from_attributes=True)

    feature: str = Field(..., description="Feature name (modules, providers, adapters, etc.)")
    status: FeatureStatus = Field(..., description="Current health status")
    degraded_reasons: list[str] = Field(
        default_factory=list,
        description="Reasons why feature is degraded (empty if healthy)",
    )
    dependencies: list[str] = Field(
        default_factory=list, description="Feature dependencies (for troubleshooting)"
    )


class CapabilityEnvelope(BaseModel):
    """
    Top-level capability envelope returned by GET /admin/capabilities.

    This is the single source of truth for what the UI should render.
    """

    model_config = ConfigDict(from_attributes=True)

    tools: list[ToolCapability] = Field(
        default_factory=list, description="Available orchestrator tools"
    )
    modules: list[ModuleCapability] = Field(
        default_factory=list, description="Installed and draft modules"
    )
    providers: list[ProviderCapability] = Field(
        default_factory=list, description="Configured LLM providers"
    )
    adapters: list[AdapterCapability] = Field(
        default_factory=list, description="Installed adapters with lock status"
    )
    features: list[FeatureHealth] = Field(
        default_factory=list, description="Per-feature health status"
    )
    config_version: str = Field(
        ..., description="Configuration version hash (for change detection)"
    )
    timestamp: str = Field(..., description="ISO 8601 timestamp of snapshot")
