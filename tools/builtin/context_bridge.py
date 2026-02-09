"""
Bridge between tool layer and dashboard aggregator.
Provides synchronous access to async dashboard data.

This module enables the user_context tool to fetch real data from the
DashboardAggregator while maintaining backward compatibility with mock data.
"""
import asyncio
import os
from typing import Dict, Any, Optional, List
import logging

logger = logging.getLogger(__name__)

# Lazy imports to avoid circular dependencies
_aggregator: Optional[Any] = None
_loop: Optional[asyncio.AbstractEventLoop] = None


def _get_aggregator(user_id: str = "default"):
    """Get or create dashboard aggregator instance."""
    global _aggregator, _loop

    if _aggregator is None:
        try:
            from dashboard_service.aggregator import DashboardAggregator, UserConfig
            config = UserConfig(user_id=user_id)
            _aggregator = DashboardAggregator(config)
            _loop = asyncio.new_event_loop()
            logger.info(f"Initialized DashboardAggregator for user: {user_id}")
        except ImportError as e:
            logger.warning(f"Could not import DashboardAggregator: {e}")
            return None
        except Exception as e:
            logger.error(f"Failed to initialize DashboardAggregator: {e}")
            return None

    return _aggregator


def fetch_context_sync(
    categories: Optional[List[str]] = None,
    user_id: str = "default",
) -> Dict[str, Any]:
    """
    Synchronous wrapper for dashboard aggregator.

    Converts async UnifiedContext to dict format expected by tools.

    Args:
        categories: Optional list of categories to fetch (e.g., ["calendar", "navigation"])
        user_id: User identifier

    Returns:
        Dict with context data or empty dict on failure
    """
    global _loop

    # Check for mock mode
    if os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true":
        logger.debug("Using mock context (USE_MOCK_CONTEXT=true)")
        return {}  # Return empty to signal caller to use mock

    aggregator = _get_aggregator(user_id)
    if aggregator is None:
        logger.warning("Aggregator not available, returning empty context")
        return {}

    try:
        # Run async in dedicated loop
        if _loop is None or _loop.is_closed():
            _loop = asyncio.new_event_loop()

        context = _loop.run_until_complete(
            aggregator.get_unified_context(categories=categories)
        )

        # Convert UnifiedContext to dict format expected by user_context.py
        if hasattr(context, 'to_dict'):
            raw_dict = context.to_dict()
            # The to_dict() returns {"user_id": ..., "context": {...}, ...}
            # We need to extract the context portion and flatten it
            result = raw_dict.get("context", {})

            # Ensure each category has the expected structure for compatibility
            # with _build_*_summary functions in user_context.py
            return _normalize_context_for_tools(result, context)
        elif hasattr(context, '__dict__'):
            return context.__dict__
        else:
            return dict(context) if context else {}

    except Exception as e:
        logger.error(f"Error fetching context: {e}")
        return {}


def _normalize_context_for_tools(context_dict: Dict[str, Any], unified_context) -> Dict[str, Any]:
    """
    Normalize the UnifiedContext output to match the format expected by
    user_context.py's _build_*_summary functions.

    The tool layer expects a slightly different structure than what
    DashboardAggregator produces, so we transform it here.
    """
    result = {}

    # Calendar: ensure 'events' list and 'today_count'
    calendar_data = context_dict.get("calendar", {})
    if calendar_data:
        events = calendar_data.get("events", [])
        # Add urgency field if not present (needed by _build_calendar_summary)
        for event in events:
            if "urgency" not in event:
                # Use CalendarEvent's urgency logic if available
                event["urgency"] = event.get("urgency", "MEDIUM")
        result["calendar"] = {
            "events": events,
            "today_count": calendar_data.get("today_count", len(events)),
        }

    # Finance: ensure proper structure
    finance_data = context_dict.get("finance", {})
    if finance_data:
        transactions = finance_data.get("transactions", [])
        result["finance"] = {
            "transactions": transactions,
            "total_expenses_period": finance_data.get("total_expenses_period", 0),
            "total_income_period": finance_data.get("total_income_period", 0),
            "net_cashflow": finance_data.get("net_cashflow", 0),
        }

    # Health: ensure proper structure
    health_data = context_dict.get("health", {})
    if health_data:
        result["health"] = {
            "steps": health_data.get("steps", 0),
            "steps_goal": health_data.get("steps_goal", 10000),
            "steps_progress": health_data.get("steps_progress", 0),
            "heart_rate": health_data.get("heart_rate"),
            "hrv": health_data.get("hrv"),
            "sleep_hours": health_data.get("sleep_hours"),
            "sleep_score": health_data.get("sleep_score"),
            "readiness": health_data.get("readiness"),
            "calories_burned": health_data.get("calories_burned"),
            "active_minutes": health_data.get("active_minutes"),
        }

    # Navigation: ensure proper structure
    nav_data = context_dict.get("navigation", {})
    if nav_data:
        primary_route = nav_data.get("primary_route", {})

        # Build saved_destinations from routes if available
        saved_destinations = {}
        routes = nav_data.get("routes", [])
        for route in routes:
            if isinstance(route, dict):
                dest = route.get("destination", {})
                if dest:
                    name = dest.get("name", "Unknown")
                    key = name.lower().replace(" ", "_")
                    saved_destinations[key] = {
                        "name": name,
                        "address": dest.get("address", ""),
                        "eta_minutes": route.get("duration_minutes", 0),
                    }

        # Transform primary_route to expected format
        formatted_route = {}
        if primary_route:
            origin = primary_route.get("origin", {})
            destination = primary_route.get("destination", {})
            formatted_route = {
                "origin": origin.get("address", "") if isinstance(origin, dict) else str(origin),
                "destination": destination.get("address", "") if isinstance(destination, dict) else str(destination),
                "destination_name": destination.get("name", "Work") if isinstance(destination, dict) else "Work",
                "duration_minutes": primary_route.get("duration_minutes", 0),
                "traffic_level": primary_route.get("traffic_level", "unknown"),
                "distance_km": primary_route.get("distance_km", 0),
            }

        result["navigation"] = {
            "primary_route": formatted_route,
            "saved_destinations": saved_destinations,
        }

    # Weather: pass through structured data
    weather_data = context_dict.get("weather", {})
    if weather_data:
        current = weather_data.get("current")
        forecasts = weather_data.get("forecasts", [])
        result["weather"] = {
            "current": current,
            "forecasts": forecasts[:8],
            "platforms": weather_data.get("platforms", []),
        }

    # Gaming: pass through structured data
    gaming_data = context_dict.get("gaming", {})
    if gaming_data:
        profiles = gaming_data.get("profiles", [])
        result["gaming"] = {
            "profiles": profiles,
            "platforms": gaming_data.get("platforms", []),
        }

    return result


def is_mock_mode() -> bool:
    """Check if mock mode is enabled."""
    return os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true"


def reset_aggregator():
    """Reset aggregator instance (useful for testing)."""
    global _aggregator, _loop
    if _loop and not _loop.is_closed():
        _loop.close()
    _aggregator = None
    _loop = None
