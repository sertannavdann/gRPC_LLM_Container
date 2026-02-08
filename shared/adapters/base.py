"""
Base Adapter Interface - Data-Oriented Design

This module defines the adapter interface using Protocols (structural typing)
rather than inheritance, enabling true data-oriented polymorphism.

Key principles:
- Adapters are pure functions: fetch_raw() → transform() → canonical data
- No inheritance hierarchy, dispatch via registry lookup
- Each adapter is responsible for ONE platform in ONE category
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import (
    Dict, Any, List, Optional, TypeVar, Generic, 
    Protocol, runtime_checkable
)
from enum import Enum
import uuid


# ============================================================================
# ADAPTER CONFIGURATION
# ============================================================================

class AdapterCategory(Enum):
    """Available adapter categories."""
    FINANCE = "finance"
    CALENDAR = "calendar"
    HEALTH = "health"
    NAVIGATION = "navigation"
    WEATHER = "weather"
    GAMING = "gaming"


@dataclass
class AdapterConfig:
    """
    Configuration for a platform adapter.
    Credentials and settings passed to adapter on instantiation.
    """
    category: AdapterCategory
    platform: str  # e.g., "wealthsimple", "google_calendar"
    credentials: Dict[str, Any] = field(default_factory=dict)
    settings: Dict[str, Any] = field(default_factory=dict)
    enabled: bool = True
    
    # Rate limiting
    rate_limit_per_minute: int = 60
    timeout_seconds: int = 30
    
    # Retry policy
    max_retries: int = 3
    retry_delay_seconds: float = 1.0


@dataclass
class AdapterResult:
    """
    Result from an adapter fetch operation.
    Includes both data and metadata about the fetch.
    """
    success: bool
    category: str
    platform: str
    data: List[Any]  # List of canonical objects
    fetched_at: datetime = field(default_factory=datetime.now)
    error: Optional[str] = None
    raw_count: int = 0
    transformed_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "category": self.category,
            "platform": self.platform,
            "data": [d.to_dict() if hasattr(d, 'to_dict') else d for d in self.data],
            "fetched_at": self.fetched_at.isoformat(),
            "error": self.error,
            "raw_count": self.raw_count,
            "transformed_count": self.transformed_count,
            "metadata": self.metadata
        }


# ============================================================================
# ADAPTER PROTOCOL (Structural Typing)
# ============================================================================

# Generic type for the canonical data type (e.g., FinancialTransaction)
T = TypeVar('T')


@runtime_checkable
class Adapter(Protocol[T]):
    """
    Protocol defining the adapter interface.
    
    Any class implementing these methods is a valid Adapter,
    regardless of inheritance. This enables duck typing with type hints.
    """
    category: str
    platform: str
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Fetch raw data from the platform API."""
        ...
    
    def transform(self, raw_data: Dict[str, Any]) -> List[T]:
        """Transform platform-specific data to canonical format."""
        ...
    
    def get_capabilities(self) -> Dict[str, bool]:
        """Return adapter capabilities (read, write, real-time, etc.)."""
        ...


# ============================================================================
# BASE ADAPTER (Abstract Implementation)
# ============================================================================

class BaseAdapter(ABC, Generic[T]):
    """
    Abstract base class for platform adapters.
    
    Provides common functionality while enforcing the adapter contract.
    Subclasses must implement fetch_raw() and transform().
    """
    
    category: str = "unknown"
    platform: str = "unknown"
    
    def __init__(self, config: Optional[AdapterConfig] = None):
        self.config = config or AdapterConfig(
            category=AdapterCategory(self.category),
            platform=self.platform
        )
        self._last_fetch: Optional[datetime] = None
        self._request_count: int = 0
    
    @abstractmethod
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """
        Fetch raw data from the platform API.
        
        This method handles:
        - Authentication using config.credentials
        - HTTP requests to the platform API
        - Error handling and retries
        
        Returns raw JSON/dict response from the API.
        """
        pass
    
    @abstractmethod
    def transform(self, raw_data: Dict[str, Any]) -> List[T]:
        """
        Transform platform-specific data to canonical format.
        
        This method handles:
        - Mapping platform fields to canonical schema
        - Type conversions (dates, decimals, enums)
        - Preserving platform-specific data in metadata
        
        Returns list of canonical objects.
        """
        pass
    
    def get_capabilities(self) -> Dict[str, bool]:
        """
        Return adapter capabilities.
        Override in subclasses to indicate supported features.
        """
        return {
            "read": True,
            "write": False,
            "real_time": False,
            "batch": True,
            "webhooks": False,
        }
    
    async def fetch(self, config: Optional[AdapterConfig] = None) -> AdapterResult:
        """
        Main entry point: fetch + transform in one call.
        
        This method orchestrates the full fetch pipeline:
        1. Validate configuration
        2. Fetch raw data from platform
        3. Transform to canonical format
        4. Return result with metadata
        """
        cfg = config or self.config
        
        try:
            # Fetch raw data
            raw_data = await self.fetch_raw(cfg)
            raw_count = self._count_raw_items(raw_data)
            
            # Transform to canonical
            canonical_data = self.transform(raw_data)
            
            self._last_fetch = datetime.now()
            self._request_count += 1
            
            return AdapterResult(
                success=True,
                category=self.category,
                platform=self.platform,
                data=canonical_data,
                raw_count=raw_count,
                transformed_count=len(canonical_data),
                metadata={
                    "request_count": self._request_count,
                    "capabilities": self.get_capabilities()
                }
            )
            
        except Exception as e:
            return AdapterResult(
                success=False,
                category=self.category,
                platform=self.platform,
                data=[],
                error=str(e),
                metadata={"exception_type": type(e).__name__}
            )
    
    def _count_raw_items(self, raw_data: Dict[str, Any]) -> int:
        """Count items in raw response (platform-specific)."""
        # Common patterns
        for key in ["items", "data", "results", "transactions", "events", "records"]:
            if key in raw_data and isinstance(raw_data[key], list):
                return len(raw_data[key])
        return 1 if raw_data else 0
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} category={self.category} platform={self.platform}>"


# ============================================================================
# MOCK ADAPTER (For Testing/Development)
# ============================================================================

class MockAdapter(BaseAdapter[T]):
    """
    Mock adapter for testing and development.
    Returns configurable mock data.
    """
    
    def __init__(self, 
                 category: str, 
                 platform: str,
                 mock_data: List[T],
                 config: Optional[AdapterConfig] = None):
        self.category = category
        self.platform = platform
        self._mock_data = mock_data
        super().__init__(config)
    
    async def fetch_raw(self, config: AdapterConfig) -> Dict[str, Any]:
        """Return mock raw data."""
        return {
            "items": [
                d.to_dict() if hasattr(d, 'to_dict') else d 
                for d in self._mock_data
            ],
            "mock": True,
            "platform": self.platform
        }
    
    def transform(self, raw_data: Dict[str, Any]) -> List[T]:
        """Return mock data directly (already canonical)."""
        return self._mock_data
