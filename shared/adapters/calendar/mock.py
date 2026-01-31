"""
Mock Calendar Adapter - Development/Testing

Generates realistic mock calendar events for UI development.
"""
from datetime import datetime, timedelta
from typing import Dict, Any, List
import random
import uuid

from ..base import BaseAdapter, AdapterConfig
from ..registry import register_adapter
from ...schemas.canonical import (
    CalendarEvent,
    EventStatus,
    EventType,
    GeoPoint,
    Contact,
    RecurrenceRule,
)


# Realistic event templates
MOCK_EVENTS = [
    {
        "title": "Team Standup",
        "duration_minutes": 15,
        "type": EventType.MEETING,
        "recurring": True,
        "attendees": ["Alice Smith", "Bob Johnson", "Carol White"],
    },
    {
        "title": "1:1 with Manager",
        "duration_minutes": 30,
        "type": EventType.MEETING,
        "recurring": True,
        "attendees": ["Sarah Manager"],
    },
    {
        "title": "Sprint Planning",
        "duration_minutes": 60,
        "type": EventType.MEETING,
        "recurring": False,
        "attendees": ["Team Alpha", "Product Owner"],
    },
    {
        "title": "Deep Work Block",
        "duration_minutes": 120,
        "type": EventType.FOCUS_TIME,
        "recurring": False,
        "attendees": [],
    },
    {
        "title": "Dentist Appointment",
        "duration_minutes": 60,
        "type": EventType.OTHER,
        "recurring": False,
        "location": "123 Health St, Toronto",
        "attendees": [],
    },
    {
        "title": "Gym Session",
        "duration_minutes": 60,
        "type": EventType.OTHER,
        "recurring": True,
        "location": "GoodLife Fitness",
        "attendees": [],
    },
    {
        "title": "Coffee with Alex",
        "duration_minutes": 45,
        "type": EventType.MEETING,
        "recurring": False,
        "location": "Starbucks Reserve",
        "attendees": ["Alex Chen"],
    },
    {
        "title": "Quarterly Review",
        "duration_minutes": 90,
        "type": EventType.MEETING,
        "recurring": False,
        "attendees": ["Entire Department"],
    },
    {
        "title": "Flight to NYC",
        "duration_minutes": 180,
        "type": EventType.OTHER,
        "recurring": False,
        "location": "Toronto Pearson Airport",
        "attendees": [],
    },
    {
        "title": "Lunch Break",
        "duration_minutes": 60,
        "type": EventType.OTHER,
        "recurring": True,
        "attendees": [],
    },
]

EVENT_COLORS = ["#4285f4", "#34a853", "#fbbc05", "#ea4335", "#9c27b0", "#00bcd4"]


@register_adapter(
    category="calendar",
    platform="mock",
    display_name="Mock Calendar",
    description="Development mock adapter with realistic calendar events",
    icon="📅",
    requires_auth=False,
)
class MockCalendarAdapter(BaseAdapter[CalendarEvent]):
    """
    Mock calendar adapter for development and testing.
    Generates realistic event data.
    """
    
    category = "calendar"
    platform = "mock"
    
    def __init__(self, config: AdapterConfig = None):
        super().__init__(config)
        self._seed = random.randint(1, 10000)
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Generate mock raw data simulating API response."""
        random.seed(self._seed)
        
        events = []
        now = datetime.now()
        
        # Generate events for the next 14 days
        for day_offset in range(-2, 14):  # Include 2 days past
            day_date = now.date() + timedelta(days=day_offset)
            
            # Generate 2-5 events per day
            num_events = random.randint(2, 5)
            
            for _ in range(num_events):
                template = random.choice(MOCK_EVENTS)
                
                # Random start hour between 8am and 6pm
                start_hour = random.randint(8, 18)
                start_minute = random.choice([0, 15, 30, 45])
                
                start_time = datetime.combine(
                    day_date, 
                    datetime.min.time().replace(hour=start_hour, minute=start_minute)
                )
                end_time = start_time + timedelta(minutes=template["duration_minutes"])
                
                # Determine status
                if start_time < now:
                    status = "confirmed"
                elif random.random() > 0.9:
                    status = "tentative"
                else:
                    status = "confirmed"
                
                events.append({
                    "id": f"mock_event_{uuid.uuid4().hex[:8]}",
                    "title": template["title"],
                    "start": start_time.isoformat(),
                    "end": end_time.isoformat(),
                    "status": status,
                    "type": template["type"].value,
                    "location": template.get("location"),
                    "attendees": template["attendees"],
                    "color": random.choice(EVENT_COLORS),
                    "is_recurring": template.get("recurring", False),
                })
        
        # Sort by start time
        events.sort(key=lambda x: x["start"])
        
        return {
            "events": events,
            "calendar_id": "mock_primary",
            "mock": True,
        }
    
    def transform(self, raw_data: Dict[str, Any]) -> List[CalendarEvent]:
        """Transform mock data to canonical format."""
        events = []
        
        for evt in raw_data.get("events", []):
            # Parse attendees
            attendees = [
                Contact(name=name, email=f"{name.lower().replace(' ', '.')}@example.com")
                for name in evt.get("attendees", [])
            ]
            
            # Parse location
            location = None
            if evt.get("location"):
                location = GeoPoint(
                    latitude=43.6532,  # Toronto coordinates as default
                    longitude=-79.3832,
                    address=evt["location"],
                )
            
            # Parse status
            status_map = {
                "confirmed": EventStatus.CONFIRMED,
                "tentative": EventStatus.TENTATIVE,
                "cancelled": EventStatus.CANCELLED,
            }
            status = status_map.get(evt.get("status"), EventStatus.CONFIRMED)
            
            # Parse event type
            event_type = EventType(evt.get("type", "other"))
            
            events.append(CalendarEvent(
                id=f"mock:{evt['id']}",
                start_time=datetime.fromisoformat(evt["start"]),
                end_time=datetime.fromisoformat(evt["end"]),
                title=evt["title"],
                location=location,
                attendees=attendees,
                status=status,
                event_type=event_type,
                color=evt.get("color"),
                calendar_id=raw_data.get("calendar_id"),
                platform=self.platform,
                metadata={
                    "raw": evt,
                    "is_recurring": evt.get("is_recurring", False),
                }
            ))
        
        return events
    
    def get_capabilities(self) -> Dict[str, bool]:
        return {
            "read": True,
            "write": False,  # Mock doesn't support write
            "real_time": False,
            "batch": True,
            "webhooks": False,
            "busy_times": True,
            "recurring": True,
        }
