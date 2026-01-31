# Data Adapters - Platform-agnostic data integration
from .base import BaseAdapter, AdapterConfig, AdapterResult
from .registry import AdapterRegistry

__all__ = [
    "BaseAdapter",
    "AdapterConfig", 
    "AdapterResult",
    "AdapterRegistry",
]
