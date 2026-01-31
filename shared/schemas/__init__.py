# Canonical data schemas for platform-agnostic data processing
from .canonical import (
    # Finance
    FinancialTransaction,
    FinancialAccount,
    TransactionCategory,
    # Calendar
    CalendarEvent,
    EventStatus,
    RecurrenceRule,
    # Health
    HealthMetric,
    MetricType,
    # Navigation
    NavigationRoute,
    TrafficLevel,
    # Common
    GeoPoint,
    Contact,
)

__all__ = [
    # Finance
    "FinancialTransaction",
    "FinancialAccount", 
    "TransactionCategory",
    # Calendar
    "CalendarEvent",
    "EventStatus",
    "RecurrenceRule",
    # Health
    "HealthMetric",
    "MetricType",
    # Navigation
    "NavigationRoute",
    "TrafficLevel",
    # Common
    "GeoPoint",
    "Contact",
]
