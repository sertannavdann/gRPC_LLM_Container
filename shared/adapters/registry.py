"""
Adapter Registry - Data-Oriented Dispatch

The registry enables polymorphism through data structure queries,
not inheritance. Adapters are looked up by (category, platform) tuple.

Usage:
    registry = AdapterRegistry()
    registry.register("finance", "wealthsimple", WealthsimpleAdapter)
    adapter_class = registry.get("finance", "wealthsimple")
    adapter = adapter_class()
"""
from typing import Dict, List, Type, Optional, Any, Callable
from dataclasses import dataclass, field
from datetime import datetime
import logging

from .base import BaseAdapter, AdapterConfig, AdapterCategory

logger = logging.getLogger(__name__)


@dataclass
class AdapterInfo:
    """Metadata about a registered adapter."""
    category: str
    platform: str
    adapter_class: Type[BaseAdapter]
    display_name: str
    description: str = ""
    icon: str = "🔌"
    requires_auth: bool = True
    auth_type: str = "oauth2"  # oauth2, api_key, basic
    auth_url: Optional[str] = None
    capabilities: Dict[str, bool] = field(default_factory=dict)
    registered_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "category": self.category,
            "platform": self.platform,
            "display_name": self.display_name,
            "description": self.description,
            "icon": self.icon,
            "requires_auth": self.requires_auth,
            "auth_type": self.auth_type,
            "auth_url": self.auth_url,
            "capabilities": self.capabilities,
        }


class AdapterRegistry:
    """
    Registry for platform-agnostic adapters.
    
    Enables polymorphism through data structure queries:
    - Register adapters by (category, platform)
    - Look up adapters without knowing concrete types
    - List available platforms per category
    """
    
    _instance: Optional['AdapterRegistry'] = None
    
    def __new__(cls) -> 'AdapterRegistry':
        """Singleton pattern for global registry."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._adapters: Dict[str, Dict[str, AdapterInfo]] = {
            "finance": {},
            "calendar": {},
            "health": {},
            "navigation": {},
            "weather": {},
            "gaming": {},
        }
        self._initialized = True
        self._register_default_adapters()
    
    def _register_default_adapters(self):
        """Register built-in mock adapters for development."""
        # These will be replaced with real adapters as they're implemented
        pass
    
    def register(
        self,
        category: str,
        platform: str,
        adapter_class: Type[BaseAdapter],
        display_name: Optional[str] = None,
        description: str = "",
        icon: str = "🔌",
        requires_auth: bool = True,
        auth_type: str = "oauth2",
        auth_url: Optional[str] = None,
    ) -> None:
        """
        Register an adapter for a category + platform combination.
        
        Args:
            category: Data category (finance, calendar, health, navigation)
            platform: Platform identifier (wealthsimple, google, etc.)
            adapter_class: The adapter class to instantiate
            display_name: Human-readable name for UI
            description: Description of the platform
            icon: Emoji or icon identifier
            requires_auth: Whether authentication is needed
            auth_type: Type of authentication (oauth2, api_key, basic)
            auth_url: URL to initiate OAuth flow
        """
        if category not in self._adapters:
            self._adapters[category] = {}
        
        # Get capabilities from adapter class
        temp_adapter = adapter_class()
        capabilities = temp_adapter.get_capabilities()
        
        info = AdapterInfo(
            category=category,
            platform=platform,
            adapter_class=adapter_class,
            display_name=display_name or platform.replace("_", " ").title(),
            description=description,
            icon=icon,
            requires_auth=requires_auth,
            auth_type=auth_type,
            auth_url=auth_url,
            capabilities=capabilities,
        )
        
        self._adapters[category][platform] = info
        logger.info(f"Registered adapter: {category}/{platform}")
    
    def get(self, category: str, platform: str) -> Type[BaseAdapter]:
        """
        Get adapter class for a specific category + platform.
        
        Raises:
            ValueError: If category or platform not found
        """
        if category not in self._adapters:
            raise ValueError(f"Unknown category: {category}. Available: {list(self._adapters.keys())}")
        
        if platform not in self._adapters[category]:
            available = list(self._adapters[category].keys())
            raise ValueError(f"Unknown platform for {category}: {platform}. Available: {available}")
        
        return self._adapters[category][platform].adapter_class
    
    def get_info(self, category: str, platform: str) -> AdapterInfo:
        """Get full adapter info including metadata."""
        if category not in self._adapters:
            raise ValueError(f"Unknown category: {category}")
        if platform not in self._adapters[category]:
            raise ValueError(f"Unknown platform: {platform}")
        return self._adapters[category][platform]
    
    def create_adapter(
        self, 
        category: str, 
        platform: str, 
        config: Optional[AdapterConfig] = None
    ) -> BaseAdapter:
        """
        Create an adapter instance with configuration.
        
        Convenience method that gets the class and instantiates it.
        """
        adapter_class = self.get(category, platform)
        return adapter_class(config)
    
    def list_platforms(self, category: str) -> List[str]:
        """List all available platforms for a category."""
        return list(self._adapters.get(category, {}).keys())
    
    def list_categories(self) -> List[str]:
        """List all available categories."""
        return list(self._adapters.keys())
    
    def list_all(self) -> Dict[str, List[AdapterInfo]]:
        """List all registered adapters grouped by category."""
        return {
            category: list(platforms.values())
            for category, platforms in self._adapters.items()
        }
    
    def list_all_flat(self) -> List[AdapterInfo]:
        """List all adapters as flat list."""
        adapters = []
        for platforms in self._adapters.values():
            adapters.extend(platforms.values())
        return adapters
    
    def has_adapter(self, category: str, platform: str) -> bool:
        """Check if an adapter is registered."""
        return (
            category in self._adapters and 
            platform in self._adapters[category]
        )
    
    def unregister(self, category: str, platform: str) -> bool:
        """
        Unregister an adapter.
        
        Returns True if adapter was found and removed.
        """
        if self.has_adapter(category, platform):
            del self._adapters[category][platform]
            logger.info(f"Unregistered adapter: {category}/{platform}")
            return True
        return False
    
    def clear(self) -> None:
        """Clear all registered adapters (for testing)."""
        for category in self._adapters:
            self._adapters[category] = {}
    
    def to_dict(self) -> Dict[str, Any]:
        """Export registry state as dict (for API responses)."""
        return {
            "categories": self.list_categories(),
            "adapters": {
                category: [info.to_dict() for info in infos]
                for category, infos in self.list_all().items()
            }
        }


# Global registry instance
adapter_registry = AdapterRegistry()


def register_adapter(
    category: str,
    platform: str,
    display_name: Optional[str] = None,
    description: str = "",
    icon: str = "🔌",
    requires_auth: bool = True,
    auth_type: str = "oauth2",
    auth_url: Optional[str] = None,
) -> Callable[[Type[BaseAdapter]], Type[BaseAdapter]]:
    """
    Decorator to register an adapter class.
    
    Usage:
        @register_adapter("finance", "wealthsimple", icon="💰")
        class WealthsimpleAdapter(BaseAdapter):
            ...
    """
    def decorator(cls: Type[BaseAdapter]) -> Type[BaseAdapter]:
        adapter_registry.register(
            category=category,
            platform=platform,
            adapter_class=cls,
            display_name=display_name,
            description=description,
            icon=icon,
            requires_auth=requires_auth,
            auth_type=auth_type,
            auth_url=auth_url,
        )
        return cls
    return decorator
