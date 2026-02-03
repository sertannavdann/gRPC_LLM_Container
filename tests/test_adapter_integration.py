"""
Integration tests for adapter data flow.

Verifies that:
1. Mock adapters are properly registered
2. DashboardAggregator fetches data correctly
3. Context bridge provides data to tools
4. User context tool returns expected format
"""
import pytest
import asyncio
from datetime import datetime

# Test adapter registration
class TestAdapterRegistration:
    """Verify all mock adapters are registered correctly."""

    def test_mock_adapters_imported(self):
        """Test that importing shared.adapters registers mock adapters."""
        from shared.adapters import adapter_registry

        # Check all categories have mock adapters
        assert adapter_registry.has_adapter("finance", "mock")
        assert adapter_registry.has_adapter("calendar", "mock")
        assert adapter_registry.has_adapter("health", "mock")
        assert adapter_registry.has_adapter("navigation", "mock")

    def test_adapter_info_available(self):
        """Test adapter metadata is available."""
        from shared.adapters import adapter_registry

        info = adapter_registry.get_info("calendar", "mock")
        assert info.display_name == "Mock Calendar"
        assert info.icon == "📅"
        assert info.requires_auth is False

    def test_list_all_adapters(self):
        """Test listing all registered adapters."""
        from shared.adapters import adapter_registry

        all_adapters = adapter_registry.list_all_flat()
        mock_adapters = [a for a in all_adapters if a.platform == "mock"]

        # Should have 4 mock adapters (one per category)
        assert len(mock_adapters) >= 4


class TestMockCalendarAdapter:
    """Test MockCalendarAdapter data generation."""

    @pytest.fixture
    def adapter(self):
        from shared.adapters.calendar.mock import MockCalendarAdapter
        from shared.adapters.base import AdapterConfig, AdapterCategory

        config = AdapterConfig(
            category=AdapterCategory.CALENDAR,
            platform="mock",
        )
        return MockCalendarAdapter(config)

    @pytest.mark.asyncio
    async def test_fetch_generates_events(self, adapter):
        """Test that fetch generates calendar events."""
        from shared.adapters.base import AdapterConfig, AdapterCategory

        config = AdapterConfig(
            category=AdapterCategory.CALENDAR,
            platform="mock",
        )
        result = await adapter.fetch(config)

        assert result.success
        assert len(result.data) > 0

        # Check event structure
        event = result.data[0]
        assert hasattr(event, 'title')
        assert hasattr(event, 'start_time')
        assert hasattr(event, 'end_time')

    @pytest.mark.asyncio
    async def test_event_has_required_fields(self, adapter):
        """Test events have all required canonical fields."""
        from shared.adapters.base import AdapterConfig, AdapterCategory
        from shared.schemas.canonical import CalendarEvent

        config = AdapterConfig(
            category=AdapterCategory.CALENDAR,
            platform="mock",
        )
        result = await adapter.fetch(config)

        for event in result.data[:5]:
            assert isinstance(event, CalendarEvent)
            assert event.id is not None
            assert event.title is not None
            assert event.start_time is not None


class TestMockNavigationAdapter:
    """Test MockNavigationAdapter data generation."""

    @pytest.fixture
    def adapter(self):
        from shared.adapters.navigation.mock import MockNavigationAdapter
        from shared.adapters.base import AdapterConfig, AdapterCategory

        config = AdapterConfig(
            category=AdapterCategory.NAVIGATION,
            platform="mock",
        )
        return MockNavigationAdapter(config)

    @pytest.mark.asyncio
    async def test_fetch_generates_routes(self, adapter):
        """Test that fetch generates navigation routes."""
        from shared.adapters.base import AdapterConfig, AdapterCategory

        config = AdapterConfig(
            category=AdapterCategory.NAVIGATION,
            platform="mock",
        )
        result = await adapter.fetch(config)

        assert result.success
        assert len(result.data) > 0

    @pytest.mark.asyncio
    async def test_route_has_duration(self, adapter):
        """Test routes have duration information."""
        from shared.adapters.base import AdapterConfig, AdapterCategory

        config = AdapterConfig(
            category=AdapterCategory.NAVIGATION,
            platform="mock",
        )
        result = await adapter.fetch(config)

        route = result.data[0]
        assert route.duration_seconds > 0
        assert route.distance_meters > 0


class TestDashboardAggregator:
    """Test DashboardAggregator unified context building."""

    @pytest.fixture
    def aggregator(self):
        from dashboard_service.aggregator import DashboardAggregator, UserConfig

        config = UserConfig(
            user_id="test_user",
            finance=["mock"],
            calendar=["mock"],
            health=["mock"],
            navigation=["mock"],
        )
        return DashboardAggregator(config)

    @pytest.mark.asyncio
    async def test_get_unified_context(self, aggregator):
        """Test fetching unified context from all adapters."""
        context = await aggregator.get_unified_context()

        assert context.user_id == "test_user"
        assert "calendar" in context.to_dict()["context"] or hasattr(context, "calendar")

    @pytest.mark.asyncio
    async def test_context_has_calendar_data(self, aggregator):
        """Test context includes calendar events."""
        context = await aggregator.get_unified_context(categories=["calendar"])

        calendar_data = context.calendar
        assert calendar_data is not None
        assert "events" in calendar_data or len(calendar_data) > 0

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

    def test_fetch_context_sync(self):
        """Test synchronous context fetching."""
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
        from tools.builtin.context_bridge import is_mock_mode

        # Test explicit mock mode
        os.environ["USE_MOCK_CONTEXT"] = "true"
        assert is_mock_mode() is True

        os.environ["USE_MOCK_CONTEXT"] = "false"
        assert is_mock_mode() is False

        # Cleanup
        del os.environ["USE_MOCK_CONTEXT"]


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

    def test_get_commute_time_unknown_destination(self):
        """Test commute time with unknown destination."""
        from tools.builtin.user_context import get_commute_time

        result = get_commute_time(destination="unknown_place_xyz")

        assert result["status"] == "error"
        assert "available_destinations" in result or "error" in result


class TestDestinationResolution:
    """Test destination alias resolution."""

    def test_resolve_work_to_office(self):
        """Test 'work' resolves to 'office'."""
        from tools.builtin.destinations import resolve_alias

        assert resolve_alias("work") == "office"
        assert resolve_alias("the office") == "office"
        assert resolve_alias("my office") == "office"

    def test_resolve_destination_with_saved(self):
        """Test full destination resolution."""
        from tools.builtin.destinations import resolve_destination

        saved = {
            "office": {"name": "Main Office", "address": "123 Main St", "eta_minutes": 20},
            "gym": {"name": "Fitness Center", "address": "456 Gym Rd", "eta_minutes": 10},
        }

        result = resolve_destination("work", saved)

        assert result is not None
        assert result["key"] == "office"
        assert result["eta_minutes"] == 20


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
