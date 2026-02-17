"""
Contract tests for capability envelope and feature health derivation.

Verifies Pydantic models serialize correctly, ETag generation is deterministic,
and feature health status derivation matches business rules.
"""

import hashlib
import json
import pytest

from shared.contracts.ui_capability_schema import (
    CapabilityEnvelope,
    ToolCapability,
    ModuleCapability,
    ProviderCapability,
    AdapterCapability,
    FeatureHealth,
    FeatureStatus,
)


def test_empty_capability_envelope_is_valid():
    """Empty envelope should be valid with all required fields."""
    envelope = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v1",
        timestamp="2026-01-01T00:00:00Z",
    )

    assert envelope.tools == []
    assert envelope.modules == []
    assert envelope.config_version == "v1"


def test_capability_envelope_serializes_to_json():
    """Envelope should serialize to JSON with all expected keys."""
    envelope = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v1",
        timestamp="2026-01-01T00:00:00Z",
    )

    json_str = envelope.model_dump_json()
    data = json.loads(json_str)

    assert "tools" in data
    assert "modules" in data
    assert "providers" in data
    assert "adapters" in data
    assert "features" in data
    assert "config_version" in data
    assert "timestamp" in data


def test_adapter_capability_with_locked():
    """Locked adapter should include missing_fields."""
    adapter = AdapterCapability(
        id="finance/wealthsimple",
        name="Wealthsimple",
        category="finance",
        locked=True,
        missing_fields=["api_key", "account_id"],
    )

    assert adapter.locked is True
    assert len(adapter.missing_fields) == 2
    assert "api_key" in adapter.missing_fields


def test_feature_health_degraded_requires_reasons():
    """DEGRADED status should have non-empty degraded_reasons."""
    health = FeatureHealth(
        feature="adapters",
        status=FeatureStatus.DEGRADED,
        degraded_reasons=["Wealthsimple locked (missing: api_key)"],
        dependencies=["credential_store"],
    )

    assert health.status == FeatureStatus.DEGRADED
    assert len(health.degraded_reasons) > 0


def test_provider_capability_with_locked_and_untested():
    """Provider can be locked AND untested."""
    provider = ProviderCapability(
        id="standard",
        name="Standard Tier",
        tier="standard",
        locked=True,
        connection_tested=False,
        last_test_ok=None,
    )

    assert provider.locked is True
    assert provider.connection_tested is False
    assert provider.last_test_ok is None


def test_module_capability_all_status_values():
    """Module should accept installed, draft, and disabled statuses."""
    for status in ["installed", "draft", "disabled"]:
        module = ModuleCapability(
            id="weather/openweather",
            name="OpenWeather",
            category="weather",
            platform="openweather",
            status=status,
        )
        assert module.status == status


def test_tool_capability_builtin_and_custom():
    """Tool capability should support builtin and custom categories."""
    builtin_tool = ToolCapability(
        name="weather",
        description="Get weather forecast",
        registered=True,
        category="builtin",
    )

    custom_tool = ToolCapability(
        name="my_tool",
        description="Custom tool",
        registered=True,
        category="custom",
    )

    assert builtin_tool.category == "builtin"
    assert custom_tool.category == "custom"


def test_etag_generation_is_deterministic():
    """Same envelope should produce same ETag."""
    envelope1 = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v1",
        timestamp="2026-01-01T00:00:00Z",
    )

    envelope2 = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v1",
        timestamp="2026-01-01T00:00:00Z",
    )

    json1 = envelope1.model_dump_json(exclude_none=True)
    json2 = envelope2.model_dump_json(exclude_none=True)

    etag1 = hashlib.sha256(json1.encode()).hexdigest()
    etag2 = hashlib.sha256(json2.encode()).hexdigest()

    assert etag1 == etag2


def test_etag_changes_when_data_changes():
    """Different envelope should produce different ETag."""
    envelope1 = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v1",
        timestamp="2026-01-01T00:00:00Z",
    )

    envelope2 = CapabilityEnvelope(
        tools=[],
        modules=[],
        providers=[],
        adapters=[],
        features=[],
        config_version="v2",  # Changed
        timestamp="2026-01-01T00:00:00Z",
    )

    json1 = envelope1.model_dump_json(exclude_none=True)
    json2 = envelope2.model_dump_json(exclude_none=True)

    etag1 = hashlib.sha256(json1.encode()).hexdigest()
    etag2 = hashlib.sha256(json2.encode()).hexdigest()

    assert etag1 != etag2


def test_feature_health_all_adapters_unlocked_is_healthy():
    """All adapters unlocked should result in HEALTHY status."""
    adapters = [
        AdapterCapability(
            id="finance/wealthsimple",
            name="Wealthsimple",
            category="finance",
            locked=False,
            missing_fields=[],
        ),
        AdapterCapability(
            id="calendar/google",
            name="Google Calendar",
            category="calendar",
            locked=False,
            missing_fields=[],
        ),
    ]

    locked_adapters = [a for a in adapters if a.locked]
    status = FeatureStatus.HEALTHY if len(locked_adapters) == 0 else FeatureStatus.DEGRADED

    assert status == FeatureStatus.HEALTHY


def test_feature_health_one_adapter_locked_is_degraded():
    """One locked adapter should result in DEGRADED status with reason."""
    adapters = [
        AdapterCapability(
            id="finance/wealthsimple",
            name="Wealthsimple",
            category="finance",
            locked=True,
            missing_fields=["api_key"],
        ),
        AdapterCapability(
            id="calendar/google",
            name="Google Calendar",
            category="calendar",
            locked=False,
            missing_fields=[],
        ),
    ]

    locked_adapters = [a for a in adapters if a.locked]
    if len(locked_adapters) > 0:
        status = FeatureStatus.DEGRADED
        reasons = [f"{a.name} locked (missing: {', '.join(a.missing_fields)})" for a in locked_adapters]
    else:
        status = FeatureStatus.HEALTHY
        reasons = []

    assert status == FeatureStatus.DEGRADED
    assert len(reasons) == 1
    assert "Wealthsimple" in reasons[0]


def test_feature_health_no_providers_unlocked_is_degraded():
    """All providers locked should result in DEGRADED status."""
    providers = [
        ProviderCapability(
            id="standard",
            name="Standard",
            tier="standard",
            locked=True,
        ),
        ProviderCapability(
            id="heavy",
            name="Heavy",
            tier="heavy",
            locked=True,
        ),
    ]

    unlocked_providers = [p for p in providers if not p.locked]
    if len(unlocked_providers) == 0:
        status = FeatureStatus.DEGRADED
        reasons = ["All LLM providers locked"]
    else:
        status = FeatureStatus.HEALTHY
        reasons = []

    assert status == FeatureStatus.DEGRADED
    assert "All LLM providers locked" in reasons


def test_feature_status_enum_values():
    """Verify all FeatureStatus enum values are accessible."""
    assert FeatureStatus.HEALTHY == "healthy"
    assert FeatureStatus.DEGRADED == "degraded"
    assert FeatureStatus.UNAVAILABLE == "unavailable"
    assert FeatureStatus.UNKNOWN == "unknown"
