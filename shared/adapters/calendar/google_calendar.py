"""
Google Calendar Adapter - Real events from Google Calendar API v3.

API docs: https://developers.google.com/calendar/api/v3/reference
Auth: OAuth2 Bearer token with automatic refresh
Required credentials: access_token, refresh_token, client_id, client_secret
"""
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, List, Optional

import aiohttp

from shared.adapters.base import BaseAdapter, AdapterConfig
from shared.adapters.registry import register_adapter
from shared.schemas.canonical import (
    CalendarEvent,
    Contact,
    EventStatus,
    EventType,
    GeoPoint,
)

logger = logging.getLogger(__name__)

CALENDAR_API = "https://www.googleapis.com/calendar/v3"
TOKEN_URL = "https://oauth2.googleapis.com/token"

_STATUS_MAP = {
    "confirmed": EventStatus.CONFIRMED,
    "tentative": EventStatus.TENTATIVE,
    "cancelled": EventStatus.CANCELLED,
}

_EVENT_TYPE_KEYWORDS = {
    EventType.MEETING: ["standup", "1:1", "one-on-one", "sync", "meeting", "review", "retro", "sprint"],
    EventType.FOCUS_TIME: ["focus", "deep work", "heads down", "no meetings"],
    EventType.OUT_OF_OFFICE: ["ooo", "out of office", "vacation", "pto", "holiday"],
    EventType.REMINDER: ["reminder", "todo", "follow up"],
}


def _infer_event_type(title: str) -> EventType:
    """Infer event type from title keywords."""
    lower = title.lower()
    for event_type, keywords in _EVENT_TYPE_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            return event_type
    return EventType.OTHER


@register_adapter(
    category="calendar",
    platform="google_calendar",
    display_name="Google Calendar",
    description="Events and schedules from Google Calendar API",
    icon="\U0001f4c5",
    requires_auth=True,
    auth_type="oauth2",
    auth_url="https://accounts.google.com/o/oauth2/v2/auth",
)
class GoogleCalendarAdapter(BaseAdapter[CalendarEvent]):
    """Adapter for Google Calendar API v3."""

    category = "calendar"
    platform = "google_calendar"

    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        access_token = config.credentials.get("access_token", "")
        refresh_token = config.credentials.get("refresh_token", "")
        client_id = config.credentials.get("client_id", "")
        client_secret = config.credentials.get("client_secret", "")

        if not access_token and not refresh_token:
            raise ValueError(
                "Google Calendar: No access_token or refresh_token configured"
            )

        calendar_id = config.settings.get("calendar_id", "primary")
        days_ahead = config.settings.get("days_ahead", 14)
        max_results = config.settings.get("max_results", 50)

        now = datetime.now(tz=timezone.utc)
        time_min = now.isoformat()
        time_max = (now + timedelta(days=days_ahead)).isoformat()

        async with aiohttp.ClientSession() as session:
            # Refresh token if we have refresh credentials
            if refresh_token and client_id and client_secret:
                access_token = await self._refresh_token(
                    session, refresh_token, client_id, client_secret
                )

            if not access_token:
                raise ValueError("Google Calendar: Could not obtain access token")

            headers = {"Authorization": f"Bearer {access_token}"}
            params = {
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
                "singleEvents": "true",
                "orderBy": "startTime",
            }

            async with session.get(
                f"{CALENDAR_API}/calendars/{calendar_id}/events",
                headers=headers,
                params=params,
                timeout=aiohttp.ClientTimeout(total=config.timeout_seconds),
            ) as resp:
                if resp.status == 401:
                    raise ValueError(
                        "Google Calendar: Unauthorized. Token may be expired or invalid."
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise ValueError(
                        f"Google Calendar API error {resp.status}: {body}"
                    )
                data = await resp.json()

        return {
            "events": data.get("items", []),
            "calendar_id": calendar_id,
            "time_zone": data.get("timeZone", "UTC"),
        }

    def transform(self, raw_data: Dict[str, Any]) -> List[CalendarEvent]:
        events = raw_data.get("events", [])
        calendar_id = raw_data.get("calendar_id", "primary")
        results = []

        for event in events:
            parsed = self._transform_event(event, calendar_id)
            if parsed:
                results.append(parsed)

        return results

    def _transform_event(
        self, event: Dict[str, Any], calendar_id: str
    ) -> Optional[CalendarEvent]:
        event_id = event.get("id", "")
        if not event_id:
            return None

        # Parse start/end times
        start = event.get("start", {})
        end = event.get("end", {})
        is_all_day = "date" in start and "dateTime" not in start

        if is_all_day:
            start_time = datetime.fromisoformat(start["date"]).replace(
                tzinfo=timezone.utc
            )
            end_time = datetime.fromisoformat(end.get("date", start["date"])).replace(
                tzinfo=timezone.utc
            )
        else:
            start_time = datetime.fromisoformat(
                start.get("dateTime", datetime.now(tz=timezone.utc).isoformat())
            )
            end_time = datetime.fromisoformat(
                end.get("dateTime", start_time.isoformat())
            )

        # Parse attendees
        attendees = []
        for att in event.get("attendees", []):
            attendees.append(
                Contact(
                    name=att.get("displayName"),
                    email=att.get("email"),
                )
            )

        # Parse organizer
        org = event.get("organizer", {})
        organizer = Contact(name=org.get("displayName"), email=org.get("email")) if org else None

        # Parse location
        location = None
        loc_str = event.get("location", "")
        if loc_str:
            location = GeoPoint(latitude=0.0, longitude=0.0, address=loc_str)

        # Status
        status = _STATUS_MAP.get(
            event.get("status", "confirmed"), EventStatus.CONFIRMED
        )

        # Event type inference
        title = event.get("summary", "")
        event_type = _infer_event_type(title)
        if is_all_day:
            event_type = EventType.ALL_DAY

        stable_id = f"gcal:{event_id}"

        return CalendarEvent(
            id=stable_id,
            start_time=start_time,
            end_time=end_time,
            title=title,
            description=event.get("description"),
            location=location,
            attendees=attendees,
            status=status,
            event_type=event_type,
            organizer=organizer,
            is_all_day=is_all_day,
            color=event.get("colorId"),
            calendar_id=calendar_id,
            platform="google_calendar",
            metadata={
                "html_link": event.get("htmlLink", ""),
                "hangout_link": event.get("hangoutLink", ""),
                "conference_data": event.get("conferenceData", {}),
                "creator": event.get("creator", {}),
                "visibility": event.get("visibility", "default"),
                "transparency": event.get("transparency", "opaque"),
            },
        )

    async def _refresh_token(
        self,
        session: aiohttp.ClientSession,
        refresh_token: str,
        client_id: str,
        client_secret: str,
    ) -> str:
        """Refresh the OAuth2 access token."""
        data = {
            "client_id": client_id,
            "client_secret": client_secret,
            "refresh_token": refresh_token,
            "grant_type": "refresh_token",
        }

        try:
            async with session.post(TOKEN_URL, data=data) as resp:
                if resp.status != 200:
                    logger.warning(
                        "Google Calendar token refresh failed: %s", await resp.text()
                    )
                    return ""
                token_data = await resp.json()
                return token_data.get("access_token", "")
        except Exception as e:
            logger.warning("Google Calendar token refresh error: %s", e)
            return ""

    @classmethod
    def normalize_category_for_tools(cls, raw_category_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize calendar data for tool consumption."""
        events = raw_category_data.get("events", [])
        for event in events:
            if "urgency" not in event:
                event["urgency"] = "MEDIUM"
        return {
            "events": events,
            "today_count": raw_category_data.get("today_count", len(events)),
        }

    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": True,
            "webhooks": False,
            "recurring_events": True,
            "attendees": True,
        }
