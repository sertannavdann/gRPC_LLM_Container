"""Provider registry for dynamic provider registration and lookup."""

import logging
from typing import Dict, Type, Optional, List
from .base_provider import BaseProvider, ProviderConfig, ProviderType, ProviderError

logger = logging.getLogger(__name__)


class ProviderRegistry:
    """
    Registry for managing available providers.

    Enables:
    - Registration of provider classes
    - Dynamic instantiation of providers via config
    - Listing available providers
    - Default provider management
    """

    def __init__(self):
        """Initialize the provider registry."""
        self._providers: Dict[ProviderType, Type[BaseProvider]] = {}
        self._instances: Dict[str, BaseProvider] = {}
        self._default_provider: Optional[str] = None

    def register(
        self,
        provider_type: ProviderType,
        provider_class: Type[BaseProvider],
    ) -> None:
        """
        Register a provider class.

        Args:
            provider_type: ProviderType enum value
            provider_class: Provider class inheriting from BaseProvider

        Raises:
            ProviderError: If provider_class doesn't inherit from BaseProvider
        """
        if not issubclass(provider_class, BaseProvider):
            raise ProviderError(
                f"Provider class {provider_class.__name__} must inherit from BaseProvider"
            )

        self._providers[provider_type] = provider_class
        logger.info(f"Registered provider: {provider_type.value} -> {provider_class.__name__}")

    def get_provider(
        self,
        config: ProviderConfig,
        name: Optional[str] = None,
    ) -> BaseProvider:
        """
        Get or create a provider instance.

        Args:
            config: ProviderConfig with provider settings
            name: Optional name for caching this instance

        Returns:
            BaseProvider instance

        Raises:
            ProviderError: If provider type not registered or instantiation fails
        """
        # Check cache
        if name and name in self._instances:
            return self._instances[name]

        # Look up provider class
        if config.provider_type not in self._providers:
            raise ProviderError(
                f"Provider {config.provider_type.value} not registered. "
                f"Available: {list(self._providers.keys())}"
            )

        provider_class = self._providers[config.provider_type]

        try:
            # Instantiate provider
            if config.provider_type == ProviderType.LOCAL:
                # Local provider gets special handling
                from .local_provider import LocalProvider

                provider = LocalProvider(config)
            else:
                # Generic instantiation for other providers
                provider = provider_class(config)

            # Cache if named
            if name:
                self._instances[name] = provider

            logger.info(f"Created provider instance: {config.provider_type.value}")
            return provider

        except Exception as e:
            raise ProviderError(
                f"Failed to instantiate provider {config.provider_type.value}: {str(e)}"
            )

    def list_available(self) -> List[str]:
        """
        List all registered provider types.

        Returns:
            List of provider type names
        """
        return [ptype.value for ptype in self._providers.keys()]

    def set_default(self, name: str) -> None:
        """
        Set default provider instance name.

        Args:
            name: Name of registered provider instance
        """
        if name not in self._instances:
            raise ProviderError(f"Provider instance '{name}' not found")
        self._default_provider = name
        logger.info(f"Set default provider: {name}")

    def get_default(self) -> Optional[BaseProvider]:
        """
        Get default provider instance.

        Returns:
            BaseProvider instance or None if not set
        """
        if self._default_provider:
            return self._instances.get(self._default_provider)
        return None

    def unregister_instance(self, name: str) -> None:
        """
        Remove a provider instance from cache.

        Args:
            name: Name of provider instance to remove
        """
        if name in self._instances:
            del self._instances[name]
            if self._default_provider == name:
                self._default_provider = None
            logger.info(f"Unregistered provider instance: {name}")


# Global registry instance
_global_registry = ProviderRegistry()


def get_registry() -> ProviderRegistry:
    """Get the global provider registry."""
    return _global_registry


def register_provider(
    provider_type: ProviderType,
    provider_class: Type[BaseProvider],
) -> None:
    """Register a provider globally."""
    _global_registry.register(provider_type, provider_class)


def get_provider(
    config: ProviderConfig,
    name: Optional[str] = None,
) -> BaseProvider:
    """Get a provider from global registry."""
    return _global_registry.get_provider(config, name)
