"""
Unit tests for shared.billing — run-unit calculator, usage store, and quota manager.

Tests run-unit formula correctness, usage storage CRUD and isolation,
and quota enforcement at boundaries (free, team, enterprise).
"""

import os
import tempfile

import pytest

from shared.billing.run_units import (
    RunUnitCalculator,
    TIER_MULTIPLIERS,
    TOOL_OVERHEADS,
)
from shared.billing.usage_store import UsageStore
from shared.billing.quota_manager import (
    QuotaManager,
    QuotaResult,
    TIER_QUOTAS,
)


# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def tmp_db(tmp_path):
    """Return a temporary SQLite DB path for UsageStore."""
    return str(tmp_path / "test_billing.db")


@pytest.fixture
def usage_store(tmp_db):
    """Create a fresh UsageStore backed by a temp DB."""
    return UsageStore(db_path=tmp_db)


@pytest.fixture
def calculator():
    """Create a RunUnitCalculator."""
    return RunUnitCalculator()


@pytest.fixture
def quota_manager(usage_store):
    """Create a QuotaManager backed by a fresh UsageStore."""
    return QuotaManager(usage_store=usage_store)


# ============================================================================
# RunUnitCalculator Tests
# ============================================================================


class TestRunUnitCalculator:
    """Tests for RunUnitCalculator formula correctness."""

    def test_basic_calculation(self, calculator):
        """Standard tier, default tool, 0.5s CPU."""
        result = calculator.calculate(cpu_seconds=0.5, tier="standard", tool_name="default")
        expected = 0.5 * 1.0 + 0.1  # 0.6
        assert abs(result - expected) < 0.001

    def test_heavy_tier_multiplier(self, calculator):
        """Heavy tier applies 1.5x multiplier."""
        result = calculator.calculate(cpu_seconds=1.0, tier="heavy")
        expected = 1.0 * 1.5 + 0.1  # 1.6
        assert abs(result - expected) < 0.001

    def test_ultra_tier_multiplier(self, calculator):
        """Ultra tier applies 3.0x multiplier."""
        result = calculator.calculate(cpu_seconds=1.0, tier="ultra")
        expected = 1.0 * 3.0 + 0.1  # 3.1
        assert abs(result - expected) < 0.001

    def test_gpu_seconds_override(self, calculator):
        """GPU seconds used when greater than CPU seconds."""
        result = calculator.calculate(cpu_seconds=0.5, gpu_seconds=2.0, tier="standard")
        expected = 2.0 * 1.0 + 0.1  # 2.1
        assert abs(result - expected) < 0.001

    def test_sandbox_tool_overhead(self, calculator):
        """sandbox_execute tool has 0.2 overhead."""
        result = calculator.calculate(cpu_seconds=1.0, tier="standard", tool_name="sandbox_execute")
        expected = 1.0 * 1.0 + 0.2  # 1.2
        assert abs(result - expected) < 0.001

    def test_build_module_overhead(self, calculator):
        """build_module tool has 0.5 overhead."""
        result = calculator.calculate(cpu_seconds=0.0, tier="standard", tool_name="build_module")
        expected = max(0.0 * 1.0 + 0.5, 0.01)  # 0.5
        assert abs(result - expected) < 0.001

    def test_minimum_floor(self, calculator):
        """Run units never drop below 0.01."""
        result = calculator.calculate(cpu_seconds=0.0, gpu_seconds=0.0, tier="standard", tool_name="default")
        # 0.0 * 1.0 + 0.1 = 0.1 > 0.01, so floor not hit here
        assert result >= 0.01

    def test_unknown_tier_defaults(self, calculator):
        """Unknown tier defaults to 1.0 multiplier."""
        result = calculator.calculate(cpu_seconds=1.0, tier="nonexistent")
        expected = 1.0 * 1.0 + 0.1  # 1.1
        assert abs(result - expected) < 0.001

    def test_from_latency_conversion(self, calculator):
        """calculate_from_latency converts ms to seconds correctly."""
        result = calculator.calculate_from_latency(latency_ms=500.0, tier="standard")
        expected = calculator.calculate(cpu_seconds=0.5, tier="standard")
        assert abs(result - expected) < 0.001

    def test_estimate_request_cost(self, calculator):
        """estimate_request_cost sums multiple tool calls."""
        calls = [
            {"tool_name": "default", "latency_ms": 500.0},
            {"tool_name": "sandbox_execute", "latency_ms": 1000.0},
        ]
        result = calculator.estimate_request_cost(calls, tier="standard")
        expected_1 = 0.5 * 1.0 + 0.1  # 0.6
        expected_2 = 1.0 * 1.0 + 0.2  # 1.2
        assert abs(result - (expected_1 + expected_2)) < 0.001

    def test_four_decimal_rounding(self, calculator):
        """Results are rounded to 4 decimal places."""
        result = calculator.calculate(cpu_seconds=0.333333, tier="standard")
        assert result == round(result, 4)


# ============================================================================
# UsageStore Tests
# ============================================================================


class TestUsageStore:
    """Tests for UsageStore CRUD and query operations."""

    def test_record_returns_id(self, usage_store):
        """Recording usage returns a non-empty record ID."""
        rid = usage_store.record("org-1", "weather_query", 0.6)
        assert rid
        assert isinstance(rid, str)
        assert len(rid) > 0

    def test_period_total_single(self, usage_store):
        """Period total returns correct value for single record."""
        usage_store.record("org-1", "test_tool", 1.5)
        total = usage_store.get_period_total("org-1")
        assert abs(total - 1.5) < 0.01

    def test_period_total_multiple(self, usage_store):
        """Period total sums multiple records."""
        usage_store.record("org-1", "tool_a", 1.0)
        usage_store.record("org-1", "tool_b", 2.0)
        usage_store.record("org-1", "tool_c", 0.5)
        total = usage_store.get_period_total("org-1")
        assert abs(total - 3.5) < 0.01

    def test_org_isolation(self, usage_store):
        """Usage records are isolated per organization."""
        usage_store.record("org-1", "tool_a", 5.0)
        usage_store.record("org-2", "tool_a", 2.0)
        assert abs(usage_store.get_period_total("org-1") - 5.0) < 0.01
        assert abs(usage_store.get_period_total("org-2") - 2.0) < 0.01

    def test_empty_org_total(self, usage_store):
        """Non-existent org returns 0.0 total."""
        total = usage_store.get_period_total("org-nonexistent")
        assert total == 0.0

    def test_usage_summary(self, usage_store):
        """Usage summary contains correct breakdowns."""
        usage_store.record("org-1", "weather_query", 0.6, tier="standard")
        usage_store.record("org-1", "build_module", 1.5, tier="heavy")
        usage_store.record("org-1", "weather_query", 0.4, tier="standard")

        summary = usage_store.get_usage_summary("org-1")
        assert summary["record_count"] == 3
        assert abs(summary["total_run_units"] - 2.5) < 0.01
        assert "weather_query" in summary["by_tool"]
        assert "build_module" in summary["by_tool"]
        assert abs(summary["by_tool"]["weather_query"] - 1.0) < 0.01
        assert "standard" in summary["by_tier"]
        assert "heavy" in summary["by_tier"]

    def test_usage_history_ordering(self, usage_store):
        """Usage history returns records in DESC order."""
        usage_store.record("org-1", "tool_a", 1.0)
        usage_store.record("org-1", "tool_b", 2.0)
        usage_store.record("org-1", "tool_c", 3.0)

        history = usage_store.get_usage_history("org-1")
        assert len(history) == 3
        # Most recent first
        assert history[0]["tool_name"] == "tool_c"
        assert history[2]["tool_name"] == "tool_a"

    def test_usage_history_limit(self, usage_store):
        """Usage history respects limit parameter."""
        for i in range(10):
            usage_store.record("org-1", f"tool_{i}", 1.0)
        history = usage_store.get_usage_history("org-1", limit=3)
        assert len(history) == 3

    def test_record_with_metadata(self, usage_store):
        """Records store optional metadata fields."""
        usage_store.record(
            "org-1", "tool_x", 1.0,
            user_id="user-42",
            thread_id="thread-abc",
            cpu_seconds=0.8,
            latency_ms=800.0,
        )
        history = usage_store.get_usage_history("org-1")
        assert len(history) == 1
        assert history[0]["user_id"] == "user-42"
        assert history[0]["thread_id"] == "thread-abc"
        assert abs(history[0]["cpu_seconds"] - 0.8) < 0.01


# ============================================================================
# QuotaManager Tests
# ============================================================================


class TestQuotaManager:
    """Tests for quota enforcement at tier boundaries."""

    def test_fresh_org_allowed(self, quota_manager):
        """A fresh organization should be within quota."""
        result = quota_manager.check_quota("org-1", plan="free")
        assert result.allowed is True
        assert result.remaining == 100.0
        assert result.plan == "free"
        assert isinstance(result, QuotaResult)

    def test_free_quota_limit(self, quota_manager, usage_store):
        """Free plan blocks at 100 RU threshold."""
        for _ in range(100):
            usage_store.record("org-1", "test_tool", 1.0)

        result = quota_manager.check_quota("org-1", plan="free")
        assert result.allowed is False
        assert result.remaining == 0.0

    def test_free_quota_just_under(self, quota_manager, usage_store):
        """Free plan allows at 99/100."""
        for _ in range(99):
            usage_store.record("org-1", "test_tool", 1.0)

        result = quota_manager.check_quota("org-1", plan="free")
        assert result.allowed is True
        assert abs(result.remaining - 1.0) < 0.1

    def test_team_quota(self, quota_manager, usage_store):
        """Team plan has 5000 RU limit."""
        result = quota_manager.check_quota("org-1", plan="team")
        assert result.allowed is True
        assert result.limit == 5000.0

    def test_enterprise_unlimited(self, quota_manager, usage_store):
        """Enterprise plan is always allowed."""
        for _ in range(200):
            usage_store.record("org-1", "test_tool", 1.0)

        result = quota_manager.check_quota("org-1", plan="enterprise")
        assert result.allowed is True
        assert result.limit == -1.0

    def test_default_plan_is_free(self, quota_manager):
        """Default plan (no explicit plan) resolves to free."""
        result = quota_manager.check_quota("org-1")
        assert result.plan == "free"

    def test_would_exceed_true(self, quota_manager, usage_store):
        """would_exceed returns True when addition crosses limit."""
        for _ in range(95):
            usage_store.record("org-1", "test_tool", 1.0)

        assert quota_manager.would_exceed("org-1", 10.0, plan="free") is True

    def test_would_exceed_false(self, quota_manager, usage_store):
        """would_exceed returns False when within budget."""
        for _ in range(10):
            usage_store.record("org-1", "test_tool", 1.0)

        assert quota_manager.would_exceed("org-1", 5.0, plan="free") is False

    def test_would_exceed_enterprise_never(self, quota_manager, usage_store):
        """Enterprise plan never exceeds."""
        for _ in range(1000):
            usage_store.record("org-1", "test_tool", 1.0)

        assert quota_manager.would_exceed("org-1", 99999.0, plan="enterprise") is False

    def test_get_remaining(self, quota_manager, usage_store):
        """get_remaining returns correct value."""
        usage_store.record("org-1", "test_tool", 30.0)
        remaining = quota_manager.get_remaining("org-1", plan="free")
        assert abs(remaining - 70.0) < 0.1

    def test_get_remaining_enterprise(self, quota_manager):
        """get_remaining returns -1.0 for unlimited plans."""
        remaining = quota_manager.get_remaining("org-1", plan="enterprise")
        assert remaining == -1.0

    def test_quota_result_model(self, quota_manager):
        """QuotaResult is a valid Pydantic model."""
        result = quota_manager.check_quota("org-1", plan="free")
        dumped = result.model_dump()
        assert "allowed" in dumped
        assert "current_usage" in dumped
        assert "limit" in dumped
        assert "remaining" in dumped
        assert "period" in dumped
        assert "org_id" in dumped
        assert "plan" in dumped


# ============================================================================
# Integration: Calculator + Store + Quota
# ============================================================================


class TestBillingIntegration:
    """End-to-end tests using calculator, store, and quota together."""

    def test_calculate_record_check(self, calculator, usage_store, quota_manager):
        """Full flow: calculate → record → check quota."""
        ru = calculator.calculate_from_latency(latency_ms=500.0, tier="standard", tool_name="default")
        usage_store.record("org-1", "default", ru)

        result = quota_manager.check_quota("org-1", plan="free")
        assert result.allowed is True
        assert result.current_usage == ru

    def test_multi_tool_request_flow(self, calculator, usage_store, quota_manager):
        """Simulate a multi-tool request with cost tracking."""
        calls = [
            {"tool_name": "weather_query", "latency_ms": 200.0},
            {"tool_name": "sandbox_execute", "latency_ms": 1500.0},
            {"tool_name": "build_module", "latency_ms": 3000.0},
        ]

        total = calculator.estimate_request_cost(calls, tier="standard")
        assert total > 0

        for call in calls:
            ru = calculator.calculate_from_latency(
                latency_ms=call["latency_ms"],
                tier="standard",
                tool_name=call["tool_name"],
            )
            usage_store.record("org-1", call["tool_name"], ru)

        summary = usage_store.get_usage_summary("org-1")
        assert summary["record_count"] == 3
        assert abs(summary["total_run_units"] - total) < 0.01
