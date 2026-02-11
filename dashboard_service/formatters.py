"""
Summary Formatters — natural language summary builders for user context data.

Moved here from tools/builtin/user_context.py to keep presentation logic
in the dashboard service (SRP). Exposed via /context/summary and /context/briefing
endpoints so both UI and orchestrator tools can consume them via HTTP.
"""

from datetime import datetime
from typing import Dict, Any, List, Optional


def build_calendar_summary(calendar_data: dict) -> str:
    """Build a natural language summary of calendar events."""
    events = calendar_data.get('events', [])
    if not events:
        return "No upcoming events scheduled."

    summaries = []

    imminent = [e for e in events if e.get('urgency') == 'HIGH']
    if imminent:
        event = imminent[0]
        summaries.append(f"IMMINENT: '{event['title']}' starting soon")

    today_count = calendar_data.get('today_count', 0)
    if today_count > 0:
        summaries.append(f"You have {today_count} events today")

    for event in events[:3]:
        start = datetime.fromisoformat(event['start_time'].replace('Z', '+00:00'))
        time_str = start.strftime('%I:%M %p')
        attendee_count = len(event.get('attendees', []))
        attendee_text = f" with {attendee_count} attendees" if attendee_count > 0 else ""
        summaries.append(f"- {event['title']} at {time_str}{attendee_text}")

    return "\n".join(summaries)


def build_finance_summary(finance_data: dict) -> str:
    """Build a natural language summary of financial status."""
    summaries = []

    net = finance_data.get('net_cashflow', 0)
    expenses = finance_data.get('total_expenses_period', 0)
    income = finance_data.get('total_income_period', 0)

    if net >= 0:
        summaries.append(f"Net cashflow: +${net:.2f} (healthy)")
    else:
        summaries.append(f"Net cashflow: ${net:.2f} (spending exceeds income)")

    summaries.append(f"- Income this period: ${income:.2f}")
    summaries.append(f"- Expenses this period: ${expenses:.2f}")

    transactions = finance_data.get('transactions', [])
    pending = [t for t in transactions if t.get('pending')]
    if pending:
        summaries.append(f"- {len(pending)} pending transaction(s)")

    merchants: Dict[str, float] = {}
    for t in transactions:
        if t.get('amount', 0) < 0:
            m = t.get('merchant', 'Unknown')
            merchants[m] = merchants.get(m, 0) + abs(t['amount'])

    if merchants:
        top = sorted(merchants.items(), key=lambda x: x[1], reverse=True)[:3]
        summaries.append(f"- Top spending: {', '.join([f'{m} (${v:.0f})' for m, v in top])}")

    return "\n".join(summaries)


def build_health_summary(health_data: dict) -> str:
    """Build a natural language summary of health metrics."""
    summaries = []

    readiness = health_data.get('readiness', 0)
    if readiness >= 70:
        summaries.append(f"Readiness: {readiness}/100 (good)")
    elif readiness >= 50:
        summaries.append(f"Readiness: {readiness}/100 (moderate)")
    else:
        summaries.append(f"Readiness: {readiness}/100 (low - consider rest)")

    steps = health_data.get('steps', 0)
    steps_goal = health_data.get('steps_goal', 10000)
    progress = (steps / steps_goal * 100) if steps_goal > 0 else 0
    summaries.append(f"- Steps: {steps:,} / {steps_goal:,} ({progress:.0f}%)")

    hrv = health_data.get('hrv', 50)
    if hrv < 40:
        summaries.append(f"Low HRV ({hrv}ms) - indicates stress or fatigue")

    sleep_hours = health_data.get('sleep_hours', 0)
    sleep_score = health_data.get('sleep_score', 0)
    summaries.append(f"- Sleep: {sleep_hours:.1f}h (score: {sleep_score}/100)")

    hr = health_data.get('heart_rate', 0)
    summaries.append(f"- Current heart rate: {hr} bpm")

    return "\n".join(summaries)


def build_navigation_summary(nav_data: dict, destination: Optional[str] = None) -> str:
    """Build a natural language summary of navigation/commute."""
    summaries = []

    if destination:
        dest_clean = destination.lower().strip()
        for word in ['the', 'my', 'to', 'go', 'drive', 'from']:
            dest_clean = dest_clean.replace(f'{word} ', '').replace(f' {word}', '')
        dest_clean = dest_clean.strip()

        saved = nav_data.get('saved_destinations', {})

        for key, dest_info in saved.items():
            dest_name = dest_info.get('name', '').lower()
            if (dest_clean in key.lower() or key.lower() in dest_clean or
                    dest_clean in dest_name or dest_name in dest_clean):
                eta = dest_info.get('eta_minutes', 0)
                name = dest_info.get('name', destination)
                address = dest_info.get('address', '')
                summaries.append(f"To {name}: approximately {eta} minutes")
                summaries.append(f"- Address: {address}")
                return "\n".join(summaries)

        available = [d.get('name', k) for k, d in saved.items()]
        return f"Destination '{destination}' not found. Available: {', '.join(available)}"

    route = nav_data.get('primary_route')
    if not route:
        return "No commute configured."

    traffic = route.get('traffic_level', 'unknown')
    duration = route.get('duration_minutes', 0)
    dest_name = route.get('destination_name', 'Work')

    if traffic == 'heavy':
        summaries.append(f"Heavy traffic! To {dest_name}: {duration} min")
    elif traffic == 'moderate':
        summaries.append(f"Moderate traffic. To {dest_name}: {duration} min")
    else:
        summaries.append(f"Light traffic. To {dest_name}: {duration} min")

    summaries.append(f"- {route.get('origin', 'Home')} -> {route.get('destination', 'Work')}")
    summaries.append(f"- Distance: {route.get('distance_km', 0):.1f} km")

    saved = nav_data.get('saved_destinations', {})
    if saved:
        dest_list = [f"{d.get('name', k)} ({d.get('eta_minutes', '?')} min)" for k, d in list(saved.items())[:4]]
        summaries.append(f"- Other destinations: {', '.join(dest_list)}")

    return "\n".join(summaries)


def build_weather_summary(weather_data: dict) -> str:
    """Build a natural language summary of weather conditions."""
    current = weather_data.get('current')
    if not current:
        return "No weather data available."

    summaries = []
    temp = current.get('temperature_celsius', 0)
    feels = current.get('feels_like_celsius', temp)
    condition = current.get('description', current.get('condition', 'unknown'))
    humidity = current.get('humidity', 0)
    wind = current.get('wind_speed_kmh', 0)

    temp_str = f"{temp:.0f}C"
    if abs(feels - temp) > 3:
        temp_str += f" (feels like {feels:.0f}C)"

    summaries.append(f"Currently: {temp_str}, {condition}")
    summaries.append(f"- Humidity: {humidity}% | Wind: {wind:.0f} km/h")

    if temp < -20:
        summaries.append("EXTREME COLD WARNING - limit outdoor exposure")
    elif temp < -10:
        summaries.append("Very cold - dress warmly")
    elif temp > 35:
        summaries.append("EXTREME HEAT WARNING - stay hydrated")

    forecasts = weather_data.get('forecasts', [])
    if forecasts:
        upcoming = forecasts[:3]
        forecast_parts = []
        for f in upcoming:
            ft = f.get('forecast_time', '')
            try:
                hour = datetime.fromisoformat(ft.replace('Z', '+00:00')).strftime('%I%p').lstrip('0')
            except (ValueError, AttributeError):
                hour = '?'
            f_temp = f.get('temperature_celsius', 0)
            f_cond = f.get('condition', '')
            precip = f.get('precipitation_probability', 0)
            precip_str = f" {int(precip * 100)}% rain" if precip > 0.2 else ""
            forecast_parts.append(f"{hour}: {f_temp:.0f}C {f_cond}{precip_str}")
        summaries.append(f"- Forecast: {' | '.join(forecast_parts)}")

    return "\n".join(summaries)


def build_gaming_summary(gaming_data: dict) -> str:
    """Build a natural language summary of gaming profile and recent activity."""
    profiles = gaming_data.get('profiles', [])
    if not profiles:
        return "No gaming data available."

    profile = profiles[0]
    summaries = []

    username = profile.get('username', 'Unknown')
    trophies = profile.get('trophies', 0)
    win_rate = profile.get('win_rate', 0)
    arena = profile.get('arena', '')
    clan = profile.get('clan_name', '')

    summaries.append(f"{username} - {trophies:,} trophies ({arena})")
    summaries.append(f"- Win rate: {win_rate * 100:.1f}% | W: {profile.get('wins', 0):,} / L: {profile.get('losses', 0):,}")
    if clan:
        summaries.append(f"- Clan: {clan}")

    battles = profile.get('metadata', {}).get('recent_battles', [])
    if battles:
        wins = sum(1 for b in battles[:10] if b.get('result') == 'win')
        total = min(len(battles), 10)
        summaries.append(f"- Recent form: {wins}/{total} wins in last {total} battles")

    return "\n".join(summaries)


def extract_high_priority_alerts(context: dict) -> List[str]:
    """Extract high priority items that need immediate attention."""
    alerts = []

    events = context.get('calendar', {}).get('events', [])
    for event in events:
        if event.get('urgency') == 'HIGH':
            alerts.append(f"'{event['title']}' starting soon")

    finance = context.get('finance', {})
    if finance.get('net_cashflow', 0) < 0:
        alerts.append("Spending exceeds income this period")

    pending = [t for t in finance.get('transactions', []) if t.get('pending')]
    if pending:
        alerts.append(f"{len(pending)} pending transaction(s) to clear")

    health = context.get('health', {})
    if health.get('hrv', 50) < 40:
        alerts.append(f"Low HRV ({health['hrv']}ms) - consider rest")

    if health.get('readiness', 70) < 50:
        alerts.append(f"Low readiness score ({health['readiness']}) - take it easy")

    nav = context.get('navigation', {})
    route = nav.get('primary_route', {})
    if route.get('traffic_level') == 'heavy':
        alerts.append(f"Heavy traffic - {route.get('duration_minutes', 0)} min commute")

    weather = context.get('weather', {})
    current = weather.get('current', {})
    temp = current.get('temperature_celsius')
    if temp is not None:
        if temp < -20:
            alerts.append(f"Extreme cold ({temp:.0f}C) - limit outdoor exposure")
        elif temp > 35:
            alerts.append(f"Extreme heat ({temp:.0f}C) - stay hydrated")

    forecasts = weather.get('forecasts', [])
    for f in forecasts[:3]:
        precip = f.get('precipitation_probability', 0)
        cond = f.get('condition', '')
        if precip > 0.7 and cond in ('rain', 'thunderstorm', 'snow'):
            alerts.append(f"High chance of {cond} coming ({int(precip * 100)}%)")
            break

    return alerts


def build_full_summary(context: dict, destination: Optional[str] = None) -> Dict[str, Any]:
    """Build a complete summary with all categories and alerts.

    Returns a dict with 'summary' (text), 'categories_retrieved', and 'alert_count'.
    """
    summaries: Dict[str, str] = {}

    if 'calendar' in context:
        summaries['calendar'] = build_calendar_summary(context['calendar'])
    if 'finance' in context:
        summaries['finance'] = build_finance_summary(context['finance'])
    if 'health' in context:
        summaries['health'] = build_health_summary(context['health'])
    if 'navigation' in context:
        summaries['navigation'] = build_navigation_summary(context['navigation'], destination=destination)
    if 'weather' in context:
        summaries['weather'] = build_weather_summary(context['weather'])
    if 'gaming' in context:
        summaries['gaming'] = build_gaming_summary(context['gaming'])

    alerts = extract_high_priority_alerts(context)

    parts = []
    if alerts:
        parts.append("HIGH PRIORITY ALERTS:")
        for alert in alerts:
            parts.append(f"  {alert}")
        parts.append("")

    section_labels = {
        'calendar': 'CALENDAR',
        'finance': 'FINANCE',
        'health': 'HEALTH',
        'navigation': 'NAVIGATION',
        'weather': 'WEATHER',
        'gaming': 'GAMING',
    }
    for key, label in section_labels.items():
        if key in summaries:
            parts.append(f"{label}:")
            parts.append(summaries[key])
            parts.append("")

    return {
        "summary": "\n".join(parts),
        "categories_retrieved": list(summaries.keys()),
        "alert_count": len(alerts),
    }
