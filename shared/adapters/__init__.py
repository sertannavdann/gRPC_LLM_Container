# Data Adapters - Platform-agnostic data integration
from .base import BaseAdapter, AdapterConfig, AdapterResult
from .registry import AdapterRegistry, adapter_registry

# Import real adapters to trigger @register_adapter decorator
from .weather.openweather import OpenWeatherAdapter
from .calendar.google_calendar import GoogleCalendarAdapter
from .gaming.clashroyale import ClashRoyaleAdapter

__all__ = [
    "BaseAdapter",
    "AdapterConfig",
    "AdapterResult",
    "AdapterRegistry",
    "adapter_registry",
    # Real adapters
    "OpenWeatherAdapter",
    "GoogleCalendarAdapter",
    "ClashRoyaleAdapter",
]
