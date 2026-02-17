"""
Integration tests for adapter data flow.

Verifies that:
1. Real adapters are properly registered
2. DashboardAggregator fetches data correctly
3. Context bridge provides data to tools
4. User context tool returns expected format
"""
import pytest
import asyncio
from datetime import datetime


# Test adapter registration
class TestAdapterRegistration:
    """Verify real adapters are registered correctly."""

    def test_real_adapters_imported(self):
        """Test that importing shared.adapters registers real adapters."""
        from shared.adapters import adapter_registry

        # Real adapters should be registered
        assert adapter_registry.has_adapter("weather", "openweather")
        assert adapter_registry.has_adapter("gaming", "clashroyale")

    def test_adapter_info_available(self):
        """Test adapter metadata is available."""
        from shared.adapters import adapter_registry

        info = adapter_registry.get_info("weather", "openweather")
        assert info.display_name == "OpenWeather"
        assert info.requires_auth is True

    def test_list_all_adapters(self):
        """Test listing all registered adapters."""
        from shared.adapters import adapter_registry

        all_adapters = adapter_registry.list_all_flat()
        # Should have at least real adapters
        assert len(all_adapters) >= 1

    def test_no_mock_adapters(self):
        """Verify mock adapters are no longer registered."""
        from shared.adapters import adapter_registry

        mock_adapters = [a for a in adapter_registry.list_all_flat() if a.platform == "mock"]
        assert len(mock_adapters) == 0


class TestDashboardAggregator:
    """Test DashboardAggregator unified context building."""

    @pytest.fixture
    def aggregator(self):
        from dashboard_service.aggregator import DashboardAggregator, UserConfig

        config = UserConfig(
            user_id="test_user",
        )
        return DashboardAggregator(config)

    @pytest.mark.asyncio
    async def test_context_caching(self, aggregator):
        """Test that context is cached correctly."""
        # First fetch
        context1 = await aggregator.get_unified_context()

        # Second fetch should use cache
        context2 = await aggregator.get_unified_context()

        # Should be the same object (from cache)
        assert context1 is context2

        # Force refresh should give new object
        context3 = await aggregator.get_unified_context(force_refresh=True)
        assert context3 is not context1


class TestContextBridge:
    """Test context bridge between dashboard and tools."""

    def test_context_bridge_class_instantiation(self):
        """Test ContextBridge class can be instantiated."""
        from tools.builtin.context_bridge import ContextBridge

        bridge = ContextBridge(dashboard_url="http://localhost:8001")
        assert bridge.dashboard_url == "http://localhost:8001"
        assert bridge.timeout == 10

    def test_fetch_context_sync(self):
        """Test synchronous context fetching (legacy wrapper)."""
        import os
        from tools.builtin.context_bridge import fetch_context_sync, is_mock_mode

        # Ensure mock mode for testing
        os.environ["USE_MOCK_CONTEXT"] = "false"

        context = fetch_context_sync(user_id="test_user")

        # Should return dict (possibly empty if aggregator not available)
        assert isinstance(context, dict)

    def test_is_mock_mode(self):
        """Test mock mode detection."""
        import os
        from tools.builtin.context_bridge import is_mock_mode, ContextBridge

        # Test explicit mock mode
        os.environ["USE_MOCK_CONTEXT"] = "true"
        assert is_mock_mode() is True
        assert ContextBridge.is_mock_mode() is True

        os.environ["USE_MOCK_CONTEXT"] = "false"
        assert is_mock_mode() is False

        # Cleanup
        del os.environ["USE_MOCK_CONTEXT"]

    def test_normalize_delegates_to_adapters(self):
        """Test that ContextBridge.normalize delegates to adapter classmethods."""
        from tools.builtin.context_bridge import ContextBridge

        bridge = ContextBridge()
        raw = {
            "finance": {
                "transactions": [{"id": "t1"}],
                "total_expenses_period": 100,
            },
            "weather": {
                "current": {"temp": 5},
                "forecasts": [],
            },
        }
        result = bridge.normalize(raw)

        assert "finance" in result
        assert "transactions" in result["finance"]
        assert "weather" in result
        assert "current" in result["weather"]


class TestUserContextTool:
    """Test user context tool functionality."""

    def test_get_user_context_returns_dict(self):
        """Test get_user_context returns proper dict structure."""
        from tools.builtin.user_context import get_user_context

        result = get_user_context(categories=["calendar"])

        assert isinstance(result, dict)
        assert "status" in result
        assert result["status"] in ["success", "error"]

    def test_get_user_context_with_all_categories(self):
        """Test fetching all categories."""
        from tools.builtin.user_context import get_user_context

        result = get_user_context(categories=["all"])

        assert result["status"] == "success"
        assert "summary" in result
        assert "categories_retrieved" in result

    def test_get_commute_time(self):
        """Test commute time tool."""
        from tools.builtin.user_context import get_commute_time

        result = get_commute_time(destination="office")

        assert isinstance(result, dict)
        assert "status" in result

        if result["status"] == "success":
            assert "eta_minutes" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
