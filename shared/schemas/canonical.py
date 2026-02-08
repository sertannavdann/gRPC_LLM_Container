"""
Canonical Data Schemas - Category-First Unified Data Structures

These schemas define platform-agnostic data structures that all adapters
transform their platform-specific data into. This enables:
- Polymorphism through data structure (not inheritance)
- Platform interoperability (mix Wealthsimple + CIBC transparently)
- Easy testing and composition
"""
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from enum import Enum
from decimal import Decimal
import uuid


# ============================================================================
# COMMON TYPES (Shared across categories)
# ============================================================================

@dataclass
class GeoPoint:
    """Unified geographic location format."""
    latitude: float
    longitude: float
    address: Optional[str] = None
    name: Optional[str] = None  # e.g., "Home", "Office"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "latitude": self.latitude,
            "longitude": self.longitude,
            "address": self.address,
            "name": self.name
        }


@dataclass
class Contact:
    """Unified contact/attendee format."""
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    avatar_url: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "email": self.email,
            "phone": self.phone,
            "avatar_url": self.avatar_url
        }


# ============================================================================
# FINANCE CATEGORY
# ============================================================================

class TransactionCategory(Enum):
    """Unified transaction categories across all platforms."""
    INCOME = "income"
    EXPENSE = "expense"
    TRANSFER = "transfer"
    INVESTMENT = "investment"
    REFUND = "refund"
    FEE = "fee"
    INTEREST = "interest"
    UNCATEGORIZED = "uncategorized"


class AccountType(Enum):
    """Unified account types."""
    CHECKING = "checking"
    SAVINGS = "savings"
    CREDIT = "credit"
    INVESTMENT = "investment"
    LOAN = "loan"
    CRYPTO = "crypto"
    OTHER = "other"


@dataclass
class FinancialTransaction:
    """
    Platform-agnostic financial transaction.
    Works for any bank/fintech: Wealthsimple, CIBC, Affirm, Chase, etc.
    """
    id: str
    timestamp: datetime
    amount: Decimal
    currency: str
    category: TransactionCategory
    merchant: str
    account_id: str
    description: Optional[str] = None
    balance_after: Optional[Decimal] = None
    pending: bool = False
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "amount": float(self.amount),
            "currency": self.currency,
            "category": self.category.value,
            "merchant": self.merchant,
            "account_id": self.account_id,
            "description": self.description,
            "balance_after": float(self.balance_after) if self.balance_after else None,
            "pending": self.pending,
            "platform": self.platform,
            "metadata": self.metadata
        }


@dataclass
class FinancialAccount:
    """
    Unified account representation across all platforms.
    """
    id: str
    name: str
    account_type: AccountType
    balance: Decimal
    currency: str
    institution: str  # "wealthsimple", "cibc", "affirm"
    mask: Optional[str] = None  # Last 4 digits
    available_balance: Optional[Decimal] = None
    credit_limit: Optional[Decimal] = None
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "account_type": self.account_type.value,
            "balance": float(self.balance),
            "currency": self.currency,
            "institution": self.institution,
            "mask": self.mask,
            "available_balance": float(self.available_balance) if self.available_balance else None,
            "credit_limit": float(self.credit_limit) if self.credit_limit else None,
            "platform": self.platform,
            "metadata": self.metadata
        }


# ============================================================================
# CALENDAR CATEGORY
# ============================================================================

class EventStatus(Enum):
    """Unified event status."""
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class EventType(Enum):
    """Unified event types."""
    MEETING = "meeting"
    REMINDER = "reminder"
    TASK = "task"
    ALL_DAY = "all_day"
    FOCUS_TIME = "focus_time"
    OUT_OF_OFFICE = "out_of_office"
    OTHER = "other"


@dataclass
class RecurrenceRule:
    """Unified recurrence specification (RFC 5545 inspired)."""
    frequency: str  # DAILY, WEEKLY, MONTHLY, YEARLY
    interval: int = 1
    count: Optional[int] = None
    until: Optional[datetime] = None
    by_day: Optional[List[str]] = None  # ["MO", "WE", "FR"]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "frequency": self.frequency,
            "interval": self.interval,
            "count": self.count,
            "until": self.until.isoformat() if self.until else None,
            "by_day": self.by_day
        }


@dataclass
class CalendarEvent:
    """
    Platform-agnostic calendar event.
    Works for Google Calendar, Apple Calendar, Outlook, etc.
    """
    id: str
    start_time: datetime
    end_time: datetime
    title: str
    description: Optional[str] = None
    location: Optional[GeoPoint] = None
    attendees: List[Contact] = field(default_factory=list)
    recurrence: Optional[RecurrenceRule] = None
    status: EventStatus = EventStatus.CONFIRMED
    event_type: EventType = EventType.OTHER
    organizer: Optional[Contact] = None
    is_all_day: bool = False
    color: Optional[str] = None
    calendar_id: Optional[str] = None
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def duration_minutes(self) -> int:
        """Calculate event duration in minutes."""
        delta = self.end_time - self.start_time
        return int(delta.total_seconds() / 60)
    
    @property
    def is_upcoming(self) -> bool:
        """Check if event is in the future."""
        return self.start_time > datetime.now()
    
    @property
    def urgency(self) -> str:
        """Calculate urgency based on time until event."""
        if self.start_time < datetime.now():
            return "PAST"
        time_until = self.start_time - datetime.now()
        if time_until < timedelta(hours=2):
            return "HIGH"
        elif time_until < timedelta(hours=24):
            return "MEDIUM"
        return "LOW"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "start_time": self.start_time.isoformat(),
            "end_time": self.end_time.isoformat(),
            "title": self.title,
            "description": self.description,
            "location": self.location.to_dict() if self.location else None,
            "attendees": [a.to_dict() for a in self.attendees],
            "recurrence": self.recurrence.to_dict() if self.recurrence else None,
            "status": self.status.value,
            "event_type": self.event_type.value,
            "organizer": self.organizer.to_dict() if self.organizer else None,
            "is_all_day": self.is_all_day,
            "color": self.color,
            "calendar_id": self.calendar_id,
            "platform": self.platform,
            "duration_minutes": self.duration_minutes,
            "urgency": self.urgency,
            "metadata": self.metadata
        }


# ============================================================================
# HEALTH CATEGORY
# ============================================================================

class MetricType(Enum):
    """Unified health metric types."""
    STEPS = "steps"
    HEART_RATE = "heart_rate"
    HRV = "hrv"
    SLEEP_DURATION = "sleep_duration"
    SLEEP_SCORE = "sleep_score"
    CALORIES_BURNED = "calories_burned"
    CALORIES_CONSUMED = "calories_consumed"
    DISTANCE = "distance"
    ACTIVE_MINUTES = "active_minutes"
    BLOOD_OXYGEN = "blood_oxygen"
    BODY_TEMPERATURE = "body_temperature"
    WEIGHT = "weight"
    BLOOD_PRESSURE_SYSTOLIC = "blood_pressure_systolic"
    BLOOD_PRESSURE_DIASTOLIC = "blood_pressure_diastolic"
    GLUCOSE = "glucose"
    STRESS = "stress"
    READINESS = "readiness"


@dataclass
class HealthMetric:
    """
    Platform-agnostic health metric.
    Works for Apple Health, Garmin, Fitbit, Oura, Whoop, etc.
    """
    id: str
    timestamp: datetime
    metric_type: MetricType
    value: float
    unit: str
    source_device: str = "unknown"
    confidence: Optional[float] = None  # 0.0-1.0 for estimated metrics
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def is_anomaly(self) -> bool:
        """Simple anomaly detection (can be extended with baselines)."""
        # Placeholder - real implementation would compare to user's baseline
        return False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "metric_type": self.metric_type.value,
            "value": self.value,
            "unit": self.unit,
            "source_device": self.source_device,
            "confidence": self.confidence,
            "platform": self.platform,
            "metadata": self.metadata
        }


@dataclass
class HealthSummary:
    """Aggregated health data for a time period."""
    date: datetime
    steps: Optional[int] = None
    avg_heart_rate: Optional[float] = None
    hrv: Optional[float] = None
    sleep_hours: Optional[float] = None
    sleep_score: Optional[int] = None
    calories_burned: Optional[int] = None
    active_minutes: Optional[int] = None
    readiness_score: Optional[int] = None
    stress_level: Optional[str] = None  # "low", "medium", "high"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "date": self.date.isoformat(),
            "steps": self.steps,
            "avg_heart_rate": self.avg_heart_rate,
            "hrv": self.hrv,
            "sleep_hours": self.sleep_hours,
            "sleep_score": self.sleep_score,
            "calories_burned": self.calories_burned,
            "active_minutes": self.active_minutes,
            "readiness_score": self.readiness_score,
            "stress_level": self.stress_level
        }


# ============================================================================
# NAVIGATION CATEGORY
# ============================================================================

class TrafficLevel(Enum):
    """Traffic congestion levels."""
    LIGHT = "light"
    MODERATE = "moderate"
    HEAVY = "heavy"
    BLOCKED = "blocked"
    UNKNOWN = "unknown"


class TransportMode(Enum):
    """Transportation modes."""
    DRIVING = "driving"
    WALKING = "walking"
    CYCLING = "cycling"
    TRANSIT = "transit"
    RIDESHARE = "rideshare"


@dataclass
class NavigationRoute:
    """
    Platform-agnostic navigation route.
    Works for Google Maps, Waze, Apple Maps, etc.
    """
    id: str
    origin: GeoPoint
    destination: GeoPoint
    waypoints: List[GeoPoint] = field(default_factory=list)
    distance_meters: float = 0.0
    duration_seconds: int = 0
    traffic_level: TrafficLevel = TrafficLevel.UNKNOWN
    estimated_arrival: Optional[datetime] = None
    transport_mode: TransportMode = TransportMode.DRIVING
    alternative_routes: List['NavigationRoute'] = field(default_factory=list)
    polyline: Optional[str] = None  # Encoded polyline for map rendering
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def distance_km(self) -> float:
        """Distance in kilometers."""
        return self.distance_meters / 1000
    
    @property
    def duration_minutes(self) -> int:
        """Duration in minutes."""
        return self.duration_seconds // 60
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "origin": self.origin.to_dict(),
            "destination": self.destination.to_dict(),
            "waypoints": [w.to_dict() for w in self.waypoints],
            "distance_meters": self.distance_meters,
            "distance_km": self.distance_km,
            "duration_seconds": self.duration_seconds,
            "duration_minutes": self.duration_minutes,
            "traffic_level": self.traffic_level.value,
            "estimated_arrival": self.estimated_arrival.isoformat() if self.estimated_arrival else None,
            "transport_mode": self.transport_mode.value,
            "polyline": self.polyline,
            "platform": self.platform,
            "metadata": self.metadata
        }


# ============================================================================
# WEATHER CATEGORY
# ============================================================================

class WeatherCondition(Enum):
    """Unified weather condition types."""
    CLEAR = "clear"
    CLOUDS = "clouds"
    RAIN = "rain"
    DRIZZLE = "drizzle"
    THUNDERSTORM = "thunderstorm"
    SNOW = "snow"
    MIST = "mist"
    FOG = "fog"
    HAZE = "haze"
    EXTREME = "extreme"


@dataclass
class WeatherData:
    """
    Platform-agnostic current weather data.
    Works for OpenWeather, WeatherAPI, AccuWeather, etc.
    """
    id: str
    timestamp: datetime
    location: GeoPoint
    temperature_celsius: float
    feels_like_celsius: float
    humidity: int  # percentage 0-100
    pressure_hpa: float
    wind_speed_ms: float
    wind_direction_deg: int
    condition: WeatherCondition
    description: str
    icon_code: str
    visibility_meters: int
    clouds_percent: int
    uv_index: Optional[float] = None
    precipitation_mm: Optional[float] = None
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def temperature_fahrenheit(self) -> float:
        return (self.temperature_celsius * 9 / 5) + 32

    @property
    def wind_speed_kmh(self) -> float:
        return self.wind_speed_ms * 3.6

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "location": self.location.to_dict(),
            "temperature_celsius": self.temperature_celsius,
            "temperature_fahrenheit": round(self.temperature_fahrenheit, 1),
            "feels_like_celsius": self.feels_like_celsius,
            "humidity": self.humidity,
            "pressure_hpa": self.pressure_hpa,
            "wind_speed_ms": self.wind_speed_ms,
            "wind_speed_kmh": round(self.wind_speed_kmh, 1),
            "wind_direction_deg": self.wind_direction_deg,
            "condition": self.condition.value,
            "description": self.description,
            "icon_code": self.icon_code,
            "visibility_meters": self.visibility_meters,
            "clouds_percent": self.clouds_percent,
            "uv_index": self.uv_index,
            "precipitation_mm": self.precipitation_mm,
            "platform": self.platform,
            "metadata": self.metadata,
        }


@dataclass
class WeatherForecast:
    """
    Platform-agnostic weather forecast data point.
    Represents a single forecast interval (e.g., 3-hour block).
    """
    id: str
    location: GeoPoint
    forecast_time: datetime
    temperature_celsius: float
    feels_like_celsius: float
    condition: WeatherCondition
    description: str
    precipitation_probability: float  # 0.0 to 1.0
    precipitation_mm: float
    humidity: int
    wind_speed_ms: float
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def temperature_fahrenheit(self) -> float:
        return (self.temperature_celsius * 9 / 5) + 32

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "location": self.location.to_dict(),
            "forecast_time": self.forecast_time.isoformat(),
            "temperature_celsius": self.temperature_celsius,
            "temperature_fahrenheit": round(self.temperature_fahrenheit, 1),
            "feels_like_celsius": self.feels_like_celsius,
            "condition": self.condition.value,
            "description": self.description,
            "precipitation_probability": self.precipitation_probability,
            "precipitation_mm": self.precipitation_mm,
            "humidity": self.humidity,
            "wind_speed_ms": self.wind_speed_ms,
            "platform": self.platform,
            "metadata": self.metadata,
        }


# ============================================================================
# GAMING CATEGORY
# ============================================================================

@dataclass
class GamingProfile:
    """
    Platform-agnostic gaming profile/stats.
    Works for Clash Royale, Clash of Clans, Brawl Stars, etc.
    """
    id: str
    username: str
    platform_tag: str  # e.g., "#ABCDEF"
    level: int
    trophies: int
    wins: int
    losses: int
    games_played: int
    clan_name: Optional[str] = None
    clan_tag: Optional[str] = None
    arena: Optional[str] = None
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def win_rate(self) -> float:
        if self.games_played == 0:
            return 0.0
        return self.wins / self.games_played

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "username": self.username,
            "platform_tag": self.platform_tag,
            "level": self.level,
            "trophies": self.trophies,
            "wins": self.wins,
            "losses": self.losses,
            "games_played": self.games_played,
            "win_rate": round(self.win_rate, 3),
            "clan_name": self.clan_name,
            "clan_tag": self.clan_tag,
            "arena": self.arena,
            "platform": self.platform,
            "metadata": self.metadata,
        }


@dataclass
class GamingMatch:
    """
    Platform-agnostic gaming match/battle record.
    """
    id: str
    timestamp: datetime
    game_type: str  # "ladder", "challenge", "tournament", "friendly"
    result: str  # "win", "loss", "draw"
    trophies_change: int
    opponent_tag: Optional[str] = None
    opponent_name: Optional[str] = None
    duration_seconds: Optional[int] = None
    platform: str = "unknown"
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat(),
            "game_type": self.game_type,
            "result": self.result,
            "trophies_change": self.trophies_change,
            "opponent_tag": self.opponent_tag,
            "opponent_name": self.opponent_name,
            "duration_seconds": self.duration_seconds,
            "platform": self.platform,
            "metadata": self.metadata,
        }


# ============================================================================
# UNIFIED CONTEXT (Dashboard Container)
# ============================================================================

@dataclass
class UnifiedContext:
    """
    The unified context object that aggregates all user data.
    This is the main output of the dashboard aggregator.
    """
    user_id: str
    finance: Dict[str, Any] = field(default_factory=dict)
    calendar: Dict[str, Any] = field(default_factory=dict)
    health: Dict[str, Any] = field(default_factory=dict)
    navigation: Dict[str, Any] = field(default_factory=dict)
    weather: Dict[str, Any] = field(default_factory=dict)
    gaming: Dict[str, Any] = field(default_factory=dict)
    relevance: Dict[str, List[Any]] = field(default_factory=lambda: {"high": [], "medium": [], "low": []})
    last_updated: Dict[str, datetime] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user_id": self.user_id,
            "context": {
                "finance": self.finance,
                "calendar": self.calendar,
                "health": self.health,
                "navigation": self.navigation,
                "weather": self.weather,
                "gaming": self.gaming,
            },
            "relevance": self.relevance,
            "last_updated": {k: v.isoformat() for k, v in self.last_updated.items()}
        }
