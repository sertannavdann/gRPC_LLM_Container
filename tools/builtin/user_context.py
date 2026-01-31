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
    }


def _build_calendar_summary(calendar_data: dict) -> str:
    """Build a natural language summary of calendar events."""
    events = calendar_data.get('events', [])
    if not events:
        return "No upcoming events scheduled."
    
    summaries = []
    
    # Imminent events (within 2 hours)
    imminent = [e for e in events if e.get('urgency') == 'HIGH']
    if imminent:
        event = imminent[0]
        summaries.append(f"⚠️ IMMINENT: '{event['title']}' starting soon")
    
    # Today's events
    today_count = calendar_data.get('today_count', 0)
    if today_count > 0:
        summaries.append(f"You have {today_count} events today")
    
    # Next few events
    for event in events[:3]:
        start = datetime.fromisoformat(event['start_time'].replace('Z', '+00:00'))
        time_str = start.strftime('%I:%M %p')
        attendee_count = len(event.get('attendees', []))
        attendee_text = f" with {attendee_count} attendees" if attendee_count > 0 else ""
        summaries.append(f"• {event['title']} at {time_str}{attendee_text}")
    
    return "\n".join(summaries)


def _build_finance_summary(finance_data: dict) -> str:
    """Build a natural language summary of financial status."""
    summaries = []
    
    net = finance_data.get('net_cashflow', 0)
    expenses = finance_data.get('total_expenses_period', 0)
    income = finance_data.get('total_income_period', 0)
    
    if net >= 0:
        summaries.append(f"💰 Net cashflow: +${net:.2f} (healthy)")
    else:
        summaries.append(f"⚠️ Net cashflow: ${net:.2f} (spending exceeds income)")
    
    summaries.append(f"• Income this period: ${income:.2f}")
    summaries.append(f"• Expenses this period: ${expenses:.2f}")
    
    # Recent pending transactions
    transactions = finance_data.get('transactions', [])
    pending = [t for t in transactions if t.get('pending')]
    if pending:
        summaries.append(f"• {len(pending)} pending transaction(s)")
    
    # Top merchants
    merchants = {}
    for t in transactions:
        if t.get('amount', 0) < 0:
            m = t.get('merchant', 'Unknown')
            merchants[m] = merchants.get(m, 0) + abs(t['amount'])
    
    if merchants:
        top = sorted(merchants.items(), key=lambda x: x[1], reverse=True)[:3]
        summaries.append(f"• Top spending: {', '.join([f'{m} (${v:.0f})' for m, v in top])}")
    
    return "\n".join(summaries)


def _build_health_summary(health_data: dict) -> str:
    """Build a natural language summary of health metrics."""
    summaries = []
    
    # Readiness score
    readiness = health_data.get('readiness', 0)
    if readiness >= 70:
        summaries.append(f"✅ Readiness: {readiness}/100 (good)")
    elif readiness >= 50:
        summaries.append(f"⚠️ Readiness: {readiness}/100 (moderate)")
    else:
        summaries.append(f"🔴 Readiness: {readiness}/100 (low - consider rest)")
    
    # Steps progress
    steps = health_data.get('steps', 0)
    steps_goal = health_data.get('steps_goal', 10000)
    progress = (steps / steps_goal * 100) if steps_goal > 0 else 0
    summaries.append(f"• Steps: {steps:,} / {steps_goal:,} ({progress:.0f}%)")
    
    # HRV alert
    hrv = health_data.get('hrv', 50)
    if hrv < 40:
        summaries.append(f"⚠️ Low HRV ({hrv}ms) - indicates stress or fatigue")
    
    # Sleep
    sleep_hours = health_data.get('sleep_hours', 0)
    sleep_score = health_data.get('sleep_score', 0)
    summaries.append(f"• Sleep: {sleep_hours:.1f}h (score: {sleep_score}/100)")
    
    # Heart rate
    hr = health_data.get('heart_rate', 0)
    summaries.append(f"• Current heart rate: {hr} bpm")
    
    return "\n".join(summaries)


def _build_navigation_summary(nav_data: dict, destination: Optional[str] = None) -> str:
    """Build a natural language summary of navigation/commute.
    
    Args:
        nav_data: Navigation context data
        destination: Optional specific destination to query (e.g., "office", "gym", "airport")
    """
    summaries = []
    
    # Check for specific destination query
    if destination:
        # Clean the destination string - remove articles and common words
        dest_clean = destination.lower().strip()
        for word in ['the', 'my', 'to', 'go', 'drive', 'from']:
            dest_clean = dest_clean.replace(f'{word} ', '').replace(f' {word}', '')
        dest_clean = dest_clean.strip()
        
        saved = nav_data.get('saved_destinations', {})
        
        # Try to match destination name with flexible matching
        matched_dest = None
        for key, dest_info in saved.items():
            dest_name = dest_info.get('name', '').lower()
            # Check if key or name contains or is contained in the query
            if (dest_clean in key.lower() or key.lower() in dest_clean or 
                dest_clean in dest_name or dest_name in dest_clean):
                matched_dest = dest_info
                break
        
        if matched_dest:
            eta = matched_dest.get('eta_minutes', 0)
            name = matched_dest.get('name', destination)
            address = matched_dest.get('address', '')
            summaries.append(f"🗺️ To {name}: approximately {eta} minutes")
            summaries.append(f"• Address: {address}")
            return "\n".join(summaries)
        else:
            # Destination not found - provide helpful message
            available = [d.get('name', k) for k, d in saved.items()]
            return f"Destination '{destination}' not found. Available: {', '.join(available)}"

    
    # Default: show primary commute route
    route = nav_data.get('primary_route')
    if not route:
        return "No commute configured."
    
    traffic = route.get('traffic_level', 'unknown')
    duration = route.get('duration_minutes', 0)
    dest_name = route.get('destination_name', 'Work')
    
    if traffic == 'heavy':
        summaries.append(f"🚨 Heavy traffic! To {dest_name}: {duration} min")
    elif traffic == 'moderate':
        summaries.append(f"⚠️ Moderate traffic. To {dest_name}: {duration} min")
    else:
        summaries.append(f"✅ Light traffic. To {dest_name}: {duration} min")
    
    summaries.append(f"• {route.get('origin', 'Home')} → {route.get('destination', 'Work')}")
    summaries.append(f"• Distance: {route.get('distance_km', 0):.1f} km")
    
    # List available destinations
    saved = nav_data.get('saved_destinations', {})
    if saved:
        dest_list = [f"{d.get('name', k)} ({d.get('eta_minutes', '?')} min)" for k, d in list(saved.items())[:4]]
        summaries.append(f"• Other destinations: {', '.join(dest_list)}")
    
    return "\n".join(summaries)


def _extract_high_priority_alerts(context: dict) -> List[str]:
    """Extract high priority items that need immediate attention."""
    alerts = []
    
    # Calendar imminent
    events = context.get('calendar', {}).get('events', [])
    for event in events:
        if event.get('urgency') == 'HIGH':
            alerts.append(f"📅 '{event['title']}' starting soon")
    
    # Budget exceeded
    finance = context.get('finance', {})
    if finance.get('net_cashflow', 0) < 0:
        alerts.append("💰 Spending exceeds income this period")
    
    # Pending transactions
    pending = [t for t in finance.get('transactions', []) if t.get('pending')]
    if pending:
        alerts.append(f"💳 {len(pending)} pending transaction(s) to clear")
    
    # Low HRV
    health = context.get('health', {})
    if health.get('hrv', 50) < 40:
        alerts.append(f"❤️ Low HRV ({health['hrv']}ms) - consider rest")
    
    # Low readiness
    if health.get('readiness', 70) < 50:
        alerts.append(f"😴 Low readiness score ({health['readiness']}) - take it easy")
    
    # Heavy traffic
    nav = context.get('navigation', {})
    route = nav.get('primary_route', {})
    if route.get('traffic_level') == 'heavy':
        alerts.append(f"🚗 Heavy traffic - {route.get('duration_minutes', 0)} min commute")
    
    return alerts


def get_user_context(
    categories: List[str] = None,
    include_alerts: bool = True,
    destination: str = None,
) -> Dict[str, Any]:
    """
    Get the user's personal context including calendar, finance, health, and navigation data.
    
    Use this tool when:
    - User asks about their schedule or upcoming events
    - User asks about their finances, spending, or budget
    - User asks about their health, fitness, or wellness
    - User asks about their commute, traffic, or driving time to a destination
    - You need context about the user's day to provide personalized advice
    - User asks "what's going on" or wants a summary
    
    Args:
        categories: Which categories to retrieve. Options: "calendar", "finance", 
                   "health", "navigation", "all". Defaults to ["all"].
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

        # Try real aggregator first (unless mock mode is forced)
        context = None
        if not is_mock_mode():
            # Map "all" to actual category list for the aggregator
            fetch_categories = None if "all" in categories else categories
            context = fetch_context_sync(categories=fetch_categories)
            if context:
                logger.debug("Using real context from DashboardAggregator")

        # Fallback to mock data if aggregator unavailable or returned empty
        if not context:
            logger.debug("Using mock context data")
            context = _get_mock_context()
        
        # Build summaries for requested categories
        summaries = {}
        
        if "all" in categories or "calendar" in categories:
            summaries['calendar'] = _build_calendar_summary(context.get('calendar', {}))
        
        if "all" in categories or "finance" in categories:
            summaries['finance'] = _build_finance_summary(context.get('finance', {}))
        
        if "all" in categories or "health" in categories:
            summaries['health'] = _build_health_summary(context.get('health', {}))
        
        if "all" in categories or "navigation" in categories:
            summaries['navigation'] = _build_navigation_summary(
                context.get('navigation', {}), 
                destination=destination
            )
        
        # Build high priority alerts
        alerts = []
        if include_alerts:
            alerts = _extract_high_priority_alerts(context)
        
        # Create formatted response
        response_parts = []
        
        if alerts:
            response_parts.append("🚨 HIGH PRIORITY ALERTS:")
            for alert in alerts:
                response_parts.append(f"  {alert}")
            response_parts.append("")
        
        if 'calendar' in summaries:
            response_parts.append("📅 CALENDAR:")
            response_parts.append(summaries['calendar'])
            response_parts.append("")
        
        if 'finance' in summaries:
            response_parts.append("💰 FINANCE:")
            response_parts.append(summaries['finance'])
            response_parts.append("")
        
        if 'health' in summaries:
            response_parts.append("❤️ HEALTH:")
            response_parts.append(summaries['health'])
            response_parts.append("")
        
        if 'navigation' in summaries:
            response_parts.append("🗺️ NAVIGATION:")
            response_parts.append(summaries['navigation'])
        
        result_text = "\n".join(response_parts)
        
        return {
            "status": "success",
            "summary": result_text,
            "categories_retrieved": list(summaries.keys()),
            "alert_count": len(alerts),
            "timestamp": datetime.now().isoformat(),
        }
        
    except Exception as e:
        logger.error(f"Failed to retrieve user context: {e}", exc_info=True)
        return {
            "status": "error",
            "error": f"Failed to retrieve user context: {str(e)}"
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
