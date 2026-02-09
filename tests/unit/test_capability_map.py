"""
Unit tests for LIDM capability-to-tier mapping.

Tests tier resolution, priority hierarchy, and endpoint discovery.
"""

import os
import sys
import pytest
from unittest.mock import patch, MagicMock

# Pre-mock the entire OpenTelemetry + observability chain so
# orchestrator/__init__.py can be imported without OTel installed.
_otel_mods = [
    "opentelemetry", "opentelemetry.trace", "opentelemetry.metrics",
    "opentelemetry.sdk", "opentelemetry.sdk.trace", "opentelemetry.sdk.trace.export",
    "opentelemetry.sdk.metrics", "opentelemetry.sdk.metrics.export",
    "opentelemetry.sdk.resources",
    "opentelemetry.exporter", "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto", "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
    "opentelemetry.exporter.prometheus",
    "opentelemetry.instrumentation", "opentelemetry.instrumentation.grpc",
    "shared.observability", "shared.observability.setup",
    "shared.observability.grpc_interceptor",
]
for _mod in _otel_mods:
    sys.modules.setdefault(_mod, MagicMock())

from orchestrator.capability_map import (
    CAPABILITY_MAP,
    get_tier_for_capability,
    get_required_tier,
    get_lidm_endpoints,
)


class TestCapabilityMap:
    """Verify the static CAPABILITY_MAP structure."""

    def test_all_entries_have_tier(self):
        for cap, entry in CAPABILITY_MAP.items():
            assert "tier" in entry, f"Missing 'tier' in capability '{cap}'"

    def test_all_entries_have_priority(self):
        for cap, entry in CAPABILITY_MAP.items():
            assert "priority" in entry, f"Missing 'priority' in capability '{cap}'"

    def test_known_heavy_tier_capabilities(self):
        for cap in ("coding", "reasoning", "analysis"):
            assert CAPABILITY_MAP[cap]["tier"] == "heavy"

    def test_known_standard_tier_capabilities(self):
        for cap in ("finance", "math", "multilingual", "fast_response", "routing", "classification", "extraction"):
            assert CAPABILITY_MAP[cap]["tier"] == "standard"

    def test_known_ultra_tier_capabilities(self):
        for cap in ("verification", "deep_research"):
            assert CAPABILITY_MAP[cap]["tier"] == "ultra"

    def test_search_is_external(self):
        assert CAPABILITY_MAP["search"]["tier"] == "external"


class TestGetTierForCapability:
    """Test single-capability → tier resolution."""

    def test_known_capability(self):
        assert get_tier_for_capability("coding") == "heavy"

    def test_unknown_capability_defaults_to_standard(self):
        assert get_tier_for_capability("nonexistent_cap") == "standard"

    def test_empty_string_defaults_to_standard(self):
        assert get_tier_for_capability("") == "standard"


class TestGetRequiredTier:
    """Test multi-capability tier escalation logic."""

    def test_single_standard_capability(self):
        assert get_required_tier(["finance"]) == "standard"

    def test_single_heavy_capability(self):
        assert get_required_tier(["coding"]) == "heavy"

    def test_single_ultra_capability(self):
        assert get_required_tier(["verification"]) == "ultra"

    def test_mixed_escalates_to_highest(self):
        """When capabilities span tiers, the highest (lowest rank) wins."""
        assert get_required_tier(["finance", "coding"]) == "heavy"

    def test_ultra_beats_heavy(self):
        assert get_required_tier(["coding", "verification"]) == "ultra"

    def test_empty_list_defaults_to_standard(self):
        assert get_required_tier([]) == "standard"

    def test_all_unknown_defaults_to_standard(self):
        assert get_required_tier(["foo", "bar"]) == "standard"

    def test_external_does_not_escalate(self):
        """'external' has the lowest priority rank — standard should win."""
        assert get_required_tier(["search", "finance"]) == "standard"

    def test_single_external_stays_standard(self):
        """A sole external capability cannot beat the default 'standard' tier."""
        assert get_required_tier(["search"]) == "standard"


class TestGetLidmEndpoints:
    """Test endpoint discovery from environment variables."""

    @patch.dict(os.environ, {}, clear=True)
    def test_defaults_when_env_absent(self):
        """Without env vars, heavy and standard use built-in defaults."""
        endpoints = get_lidm_endpoints()
        assert "heavy" in endpoints
        assert "standard" in endpoints
        assert "ultra" not in endpoints  # default ultra is ""

    @patch.dict(os.environ, {
        "LLM_HEAVY_HOST": "gpu_box:50051",
        "LLM_STANDARD_HOST": "cpu_box:50061",
        "LLM_ULTRA_HOST": "airllm_box:50062",
    }, clear=True)
    def test_custom_endpoints_from_env(self):
        endpoints = get_lidm_endpoints()
        assert endpoints["heavy"] == "gpu_box:50051"
        assert endpoints["standard"] == "cpu_box:50061"
        assert endpoints["ultra"] == "airllm_box:50062"

    @patch.dict(os.environ, {"LLM_ULTRA_HOST": ""}, clear=True)
    def test_ultra_omitted_when_empty(self):
        endpoints = get_lidm_endpoints()
        assert "ultra" not in endpoints
