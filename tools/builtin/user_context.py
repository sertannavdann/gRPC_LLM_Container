"""
User Context Tool

Provides the LLM with access to user's personal context data from the dashboard.
Enables task-oriented responses based on calendar, finance, health, and navigation data.

Tools:
- get_user_context: Retrieve user's personal context by category
- get_daily_briefing: Get a complete morning briefing

Following Google ADK patterns - simple functions returning Dict[str, Any] with status key.
"""

from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import logging

from .context_bridge import fetch_context_sync, is_mock_mode

logger = logging.getLogger(__name__)


def _get_mock_context() -> dict:
    """Get mock context data - matches dashboard API format."""
    now = datetime.now()
    
    # Calendar events
    events = []
    for i in range(5):
        start = now + timedelta(hours=i * 2 + 1)
        events.append({
            'id': f'event_{i}',
            'title': ['Team Standup', '1:1 with Manager', 'Sprint Planning', 'Deep Work', 'Lunch'][i % 5],
            'start_time': start.isoformat(),
            'end_time': (start + timedelta(hours=1)).isoformat(),
            'urgency': 'HIGH' if i == 0 else 'MEDIUM' if i < 3 else 'LOW',
            'attendees': [{'name': 'Alice', 'email': 'alice@example.com'}] if i % 2 == 0 else [],
        })
    
    # Financial transactions
    transactions = []
    for i in range(10):
        amount = -50 - (i * 15) if i % 3 != 0 else 500 + (i * 100)
        transactions.append({
            'id': f'txn_{i}',
            'merchant': ['Starbucks', 'Amazon', 'Uber Eats', 'Payroll', 'Netflix'][i % 5],
            'amount': amount,
            'currency': 'CAD',
            'timestamp': (now - timedelta(days=i)).isoformat(),
            'pending': i == 0,
        })
    
    # Health metrics
    health = {
        'steps': 6234,
        'steps_goal': 10000,
        'steps_progress': 0.6234,
        'heart_rate': 72,
        'hrv': 48,
        'sleep_hours': 7.2,
        'sleep_score': 78,
        'readiness': 72,
        'calories_burned': 1876,
        'active_minutes': 32,
    }
    
    # Navigation - with destination info
    navigation = {
        'primary_route': {
            'origin': '123 Home St, Toronto',
            'destination': '456 King St W, Toronto',
            'destination_name': 'Office',
            'duration_minutes': 20,
            'traffic_level': 'moderate',
            'distance_km': 4.5,
        },
        'saved_destinations': {
            'office': {'name': 'Office', 'address': '456 King St W, Toronto', 'eta_minutes': 20},
            'work': {'name': 'Office', 'address': '456 King St W, Toronto', 'eta_minutes': 20},  # alias for office
            'gym': {'name': 'Gym', 'address': '789 Queen St W, Toronto', 'eta_minutes': 12},
            'grocery': {'name': 'Grocery Store', 'address': '321 Bloor St W, Toronto', 'eta_minutes': 8},
            'airport': {'name': 'Toronto Pearson Airport', 'address': 'Pearson Intl Airport', 'eta_minutes': 35},
        }
    }
    
    # Weather conditions
    weather = {
        'current': {
            'temperature_celsius': -5.2,
            'feels_like_celsius': -11.0,
            'humidity': 72,
            'wind_speed_kmh': 18.5,
            'condition': 'clouds',
            'description': 'overcast clouds',
            'visibility_meters': 10000,
        },
        'forecasts': [
            {'forecast_time': (now + timedelta(hours=3)).isoformat(), 'temperature_celsius': -3.0, 'condition': 'snow', 'precipitation_probability': 0.65},
            {'forecast_time': (now + timedelta(hours=6)).isoformat(), 'temperature_celsius': -1.0, 'condition': 'clouds', 'precipitation_probability': 0.2},
        ],
        'platforms': ['mock'],
    }

    # Gaming profile
    gaming = {
        'profiles': [{
            'username': 'Player1',
            'platform_tag': '#MOCK123',
            'level': 14,
            'trophies': 6200,
            'wins': 1234,
            'losses': 890,
            'games_played': 2124,
            'win_rate': 0.581,
            'clan_name': 'MockClan',
            'arena': 'Legendary Arena',
            'platform': 'mock',
            'metadata': {'recent_battles': []},
        }],
        'platforms': ['mock'],
    }

    return {
        'calendar': {'events': events, 'today_count': 4},
        'finance': {
            'transactions': transactions,
            'total_expenses_period': 1543.21,
            'total_income_period': 2500.00,
            'net_cashflow': 956.79,
        },
        'health': health,
        'navigation': navigation,
        'weather': weather,
        'gaming': gaming,
    }


def _fetch_summary_from_dashboard(
    user_id: str = "default",
    destination: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """Fetch pre-built summary from dashboard formatters endpoint."""
    import requests
    dashboard_url = __import__("os").getenv("DASHBOARD_URL", "http://dashboard:8001")
    try:
        params: Dict[str, str] = {}
        if destination:
            params["destination"] = destination
        resp = requests.get(
            f"{dashboard_url}/context/summary/{user_id}",
            params=params,
            timeout=10,
        )
        if resp.status_code == 200:
            return resp.json()
    except Exception as e:
        logger.warning(f"Dashboard summary endpoint unreachable: {e}")
    return None


def get_user_context(
    categories: List[str] = None,
    include_alerts: bool = True,
    destination: str = None,
) -> Dict[str, Any]:
    """
    Get the user's personal context including calendar, finance, health, navigation, weather, and gaming data.

    Use this tool when:
    - User asks about their schedule or upcoming events
    - User asks about their finances, spending, or budget
    - User asks about their health, fitness, or wellness
    - User asks about their commute, traffic, or driving time to a destination
    - User asks about the weather, temperature, or forecast
    - User asks about their gaming stats, trophies, or recent battles
    - You need context about the user's day to provide personalized advice
    - User asks "what's going on" or wants a summary

    Args:
        categories: Which categories to retrieve. Options: "calendar", "finance",
                   "health", "navigation", "weather", "gaming", "all". Defaults to ["all"].
        include_alerts: Whether to include high-priority alerts. Defaults to True.
        destination: Optional specific destination to query for navigation
                    (e.g., "office", "gym", "airport", "grocery").
    
    Returns:
        Dict with status key:
            - status: "success" or "error"
            - summary: Human-readable context summary
            - categories_retrieved: List of categories included
            - alert_count: Number of high-priority alerts
    
    Example:
        >>> result = get_user_context(categories=["navigation"], destination="airport")
        >>> if result["status"] == "success":
        ...     print(result["summary"])
    """
    try:
        if categories is None:
            categories = ["all"]

        logger.debug(f"Getting user context for categories: {categories}, destination: {destination}")

        # Try dashboard summary endpoint first (single source of truth for formatting)
        if not is_mock_mode() and "all" in categories:
            result = _fetch_summary_from_dashboard(destination=destination)
            if result and result.get("summary"):
                return {
                    "status": "success",
                    "summary": result["summary"],
                    "categories_retrieved": result.get("categories_retrieved", []),
                    "alert_count": result.get("alert_count", 0),
                    "timestamp": result.get("timestamp", datetime.now().isoformat()),
                }

        # Fallback: fetch raw context and build summaries locally
        # (needed for mock mode or when dashboard is unreachable)
        context = None
        if not is_mock_mode():
            fetch_categories = None if "all" in categories else categories
            context = fetch_context_sync(categories=fetch_categories)
            if context:
                logger.debug("Using real context from DashboardAggregator")

        if not context:
            logger.debug("Using mock context data")
            context = _get_mock_context()

        # Import formatters locally to avoid circular imports at module level
        try:
            from dashboard_service.formatters import build_full_summary
            result = build_full_summary(context, destination=destination)
        except ImportError:
            # Running outside Docker (tests, dev) — use inline fallback
            result = _build_fallback_summary(context, categories, destination, include_alerts)

        return {
            "status": "success",
            "summary": result.get("summary", ""),
            "categories_retrieved": result.get("categories_retrieved", []),
            "alert_count": result.get("alert_count", 0),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"Failed to retrieve user context: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to retrieve user context: {str(e)}"
        }


def _build_fallback_summary(
    context: dict,
    categories: List[str],
    destination: Optional[str],
    include_alerts: bool,
) -> Dict[str, Any]:
    """Minimal inline summary builder for when dashboard_service.formatters is unavailable."""
    parts = []
    cats = []

    for cat in ['calendar', 'finance', 'health', 'navigation', 'weather', 'gaming']:
        if "all" in categories or cat in categories:
            data = context.get(cat)
            if data:
                cats.append(cat)
                parts.append(f"{cat.upper()}: data available")

    return {
        "summary": "\n".join(parts) if parts else "No context data available.",
        "categories_retrieved": cats,
        "alert_count": 0,
    }


def get_daily_briefing() -> Dict[str, Any]:
    """
    Get a quick daily briefing summary for the user.
    
    This provides a concise overview of the most important items across all 
    categories. Use when user asks:
    - "What's my day look like?"
    - "Give me a briefing"  
    - "What do I need to know today?"
    - "Morning summary"
    
    Returns:
        Dict with status key:
            - status: "success" or "error"
            - summary: Complete daily briefing text
            - categories_retrieved: All categories included
            - alert_count: Number of alerts requiring attention
    
    Example:
        >>> result = get_daily_briefing()
        >>> if result["status"] == "success":
        ...     print(result["summary"])
    """
    return get_user_context(categories=["all"], include_alerts=True)


def get_commute_time(destination: str = None) -> Dict[str, Any]:
    """
    Get estimated commute/travel time to a destination.
    
    Use this tool when user asks:
    - "How long to get to work?"
    - "What's my commute time?"
    - "How long to the airport?"
    - "ETA to [destination]?"
    
    Args:
        destination: The destination to get travel time for.
                    Options: "office", "gym", "grocery", "airport", or leave
                    empty for default commute route.
    
    Returns:
        Dict with status key:
            - status: "success" or "error"  
            - summary: Travel time information
            - eta_minutes: Estimated travel time in minutes
            - traffic_level: Current traffic conditions
    
    Example:
        >>> result = get_commute_time(destination="airport")
        >>> if result["status"] == "success":
        ...     print(f"ETA: {result['eta_minutes']} minutes")
    """
    try:
        # Try real aggregator first
        context = None
        if not is_mock_mode():
            context = fetch_context_sync(categories=["navigation"])
            if context:
                logger.debug("Using real navigation context from DashboardAggregator")

        # Fallback to mock data
        if not context:
            logger.debug("Using mock navigation context")
            context = _get_mock_context()

        nav_data = context.get('navigation', {})
        
        if destination:
            # Clean the destination string - remove articles and common words
            dest_clean = destination.lower().strip()
            for word in ['the', 'my', 'to', 'go', 'drive', 'from', 'work', 'place']:
                dest_clean = dest_clean.replace(f'{word} ', '').replace(f' {word}', '')
            dest_clean = dest_clean.strip()
            
            saved = nav_data.get('saved_destinations', {})
            
            # Try to match destination with flexible matching
            for key, dest_info in saved.items():
                dest_name = dest_info.get('name', '').lower()
                dest_address = dest_info.get('address', '').lower()
                # Check if key, name, or address contains or is contained in the query
                if (dest_clean in key.lower() or key.lower() in dest_clean or 
                    dest_clean in dest_name or dest_name in dest_clean or
                    dest_clean in dest_address or dest_address in dest_clean):
                    eta = dest_info.get('eta_minutes', 0)
                    name = dest_info.get('name', destination)
                    address = dest_info.get('address', '')
                    
                    return {
                        "status": "success",
                        "summary": f"To {name}: approximately {eta} minutes\nAddress: {address}",
                        "destination": name,
                        "address": address,
                        "eta_minutes": eta,
                        "traffic_level": "moderate",  # mock
                    }
            
            # Not found
            available = [d.get('name', k) for k, d in saved.items()]
            return {
                "status": "error",
                "error": f"Destination '{destination}' not found",
                "available_destinations": available,
            }
        
        # Default commute
        route = nav_data.get('primary_route', {})
        if not route:
            return {
                "status": "error",
                "error": "No default commute route configured"
            }
        
        eta = route.get('duration_minutes', 0)
        traffic = route.get('traffic_level', 'unknown')
        dest_name = route.get('destination_name', 'Work')
        
        traffic_emoji = {"light": "✅", "moderate": "⚠️", "heavy": "🚨"}.get(traffic, "")
        
        return {
            "status": "success",
            "summary": f"{traffic_emoji} To {dest_name}: {eta} minutes ({traffic} traffic)",
            "destination": dest_name,
            "address": route.get('destination', ''),
            "eta_minutes": eta,
            "traffic_level": traffic,
            "distance_km": route.get('distance_km', 0),
        }
        
    except Exception as e:
        logger.error(f"Failed to get commute time: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to get commute time: {str(e)}"
        }
