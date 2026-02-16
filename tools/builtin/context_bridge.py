"""
Bridge between tool layer and dashboard service.
Fetches real context data via HTTP from the dashboard REST API.

The orchestrator runs in a separate container from the dashboard service,
so we use HTTP calls instead of direct Python imports.
"""
import os
from typing import Dict, Any, Optional, List
import logging

import requests

logger = logging.getLogger(__name__)

DASHBOARD_URL = os.getenv("DASHBOARD_URL", "http://dashboard:8001")
_REQUEST_TIMEOUT = 10  # seconds


def fetch_context_sync(
    categories: Optional[List[str]] = None,
    user_id: str = "default",
) -> Dict[str, Any]:
    """
    Fetch unified context from the dashboard service via HTTP.

    Args:
        categories: Optional list of categories to fetch (e.g., ["calendar", "navigation"])
        user_id: User identifier

    Returns:
        Dict with context data or empty dict on failure
    """
    # Check for mock mode
    if os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true":
        logger.debug("Using mock context (USE_MOCK_CONTEXT=true)")
        return {}

    api_key = os.getenv("DASHBOARD_API_KEY") or os.getenv("INTERNAL_API_KEY")
    headers = {"X-API-Key": api_key} if api_key else None

    # If specific categories requested, fetch each one
    if categories:
        result = {}
        for category in categories:
            try:
                resp = requests.get(
                    f"{DASHBOARD_URL}/context/{category}",
                    params={"user_id": user_id},
                    headers=headers,
                    timeout=_REQUEST_TIMEOUT,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    # /context/{category} returns {"category": ..., "data": {...}}
                    result[category] = data.get("data", {})
                else:
                    logger.warning(f"Dashboard returned {resp.status_code} for {category}")
            except requests.RequestException as e:
                logger.warning(f"Failed to fetch {category} context: {e}")
        return _normalize_context_for_tools(result)

    # Fetch full unified context
    try:
        resp = requests.get(
            f"{DASHBOARD_URL}/context",
            params={"user_id": user_id},
            headers=headers,
            timeout=_REQUEST_TIMEOUT,
        )
        if resp.status_code == 200:
            raw_dict = resp.json()
            # /context returns {"user_id": ..., "context": {...}, ...}
            context_data = raw_dict.get("context", raw_dict)
            return _normalize_context_for_tools(context_data)
        else:
            logger.warning(f"Dashboard returned {resp.status_code} for unified context")
            return {}
    except requests.RequestException as e:
        logger.warning(f"Dashboard unreachable at {DASHBOARD_URL}: {e}")
        return {}


def _normalize_context_for_tools(context_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize dashboard API response to match the format expected by
    user_context.py's _build_*_summary functions.
    """
    result = {}

    # Calendar
    calendar_data = context_dict.get("calendar", {})
    if calendar_data:
        events = calendar_data.get("events", [])
        for event in events:
            if "urgency" not in event:
                event["urgency"] = "MEDIUM"
        result["calendar"] = {
            "events": events,
            "today_count": calendar_data.get("today_count", len(events)),
        }

    # Finance
    finance_data = context_dict.get("finance", {})
    if finance_data:
        result["finance"] = {
            "transactions": finance_data.get("transactions", []),
            "total_expenses_period": finance_data.get("total_expenses_period", 0),
            "total_income_period": finance_data.get("total_income_period", 0),
            "net_cashflow": finance_data.get("net_cashflow", 0),
        }

    # Health
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

    # Navigation
    nav_data = context_dict.get("navigation", {})
    if nav_data:
        primary_route = nav_data.get("primary_route", {})
        saved_destinations = {}
        for route in nav_data.get("routes", []):
            if isinstance(route, dict):
                dest = route.get("destination", {})
                if dest:
                    name = dest.get("name")
                    if not isinstance(name, str) or not name.strip():
                        name = "Unknown"
                    key = name.lower().replace(" ", "_")
                    saved_destinations[key] = {
                        "name": name,
                        "address": dest.get("address", ""),
                        "eta_minutes": route.get("duration_minutes", 0),
                    }

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

    # Weather
    weather_data = context_dict.get("weather", {})
    if weather_data:
        result["weather"] = {
            "current": weather_data.get("current"),
            "forecasts": weather_data.get("forecasts", [])[:8],
            "platforms": weather_data.get("platforms", []),
        }

    # Gaming
    gaming_data = context_dict.get("gaming", {})
    if gaming_data:
        result["gaming"] = {
            "profiles": gaming_data.get("profiles", []),
            "platforms": gaming_data.get("platforms", []),
        }

    return result


def is_mock_mode() -> bool:
    """Check if mock mode is enabled."""
    return os.getenv("USE_MOCK_CONTEXT", "false").lower() == "true"
