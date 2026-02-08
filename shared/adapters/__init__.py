# Data Adapters - Platform-agnostic data integration
from .base import BaseAdapter, AdapterConfig, AdapterResult
from .registry import AdapterRegistry, adapter_registry

# Import mock adapters to trigger @register_adapter decorator
# These provide development data when real adapters aren't configured
from .finance.mock import MockFinanceAdapter
from .calendar.mock import MockCalendarAdapter
from .health.mock import MockHealthAdapter
from .navigation.mock import MockNavigationAdapter

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
    # Mock adapters
    "MockFinanceAdapter",
    "MockCalendarAdapter",
    "MockHealthAdapter",
    "MockNavigationAdapter",
    # Real adapters
    "OpenWeatherAdapter",
    "GoogleCalendarAdapter",
    "ClashRoyaleAdapter",
]
