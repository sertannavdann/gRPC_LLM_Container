"""
Provider Router for dynamic provider selection with fallback chains.

Week 3 Architecture Roadmap - Provider Router Module

This module provides intelligent routing between LLM providers based on:
- Query complexity estimation
- Provider health and availability
- Fallback chains for resilience
- Context-aware provider selection

Integrates with the existing provider system in shared/providers/.
"""

import logging
import time
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
from enum import Enum

from shared.providers import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ProviderConfigLoader,
    get_registry,
    setup_providers,
    ProviderError,
)

logger = logging.getLogger(__name__)


class ComplexityLevel(Enum):
    """Query complexity levels for provider selection."""

    LOW = "low"           # Simple queries - local provider preferred
    MEDIUM = "medium"     # Moderate queries - online providers acceptable
    HIGH = "high"         # Complex queries - powerful providers needed
    SEARCH = "search"     # Queries requiring real-time search


@dataclass
class ProviderHealth:
    """Tracks health status of a provider."""

    provider_name: str
    is_healthy: bool = True
    unhealthy_until: float = 0.0  # Unix timestamp
    consecutive_failures: int = 0
    total_requests: int = 0
    successful_requests: int = 0
    average_latency_ms: float = 0.0
    last_check_time: float = 0.0

    @property
    def success_rate(self) -> float:
        """Calculate success rate percentage."""
        if self.total_requests == 0:
            return 100.0
        return (self.successful_requests / self.total_requests) * 100

    def is_available(self) -> bool:
        """Check if provider is currently available."""
        if not self.is_healthy:
            # Check if unhealthy period has expired
            if time.time() >= self.unhealthy_until:
                self.is_healthy = True
                self.consecutive_failures = 0
                logger.info(f"Provider {self.provider_name} health restored after timeout")
            return self.is_healthy
        return True


@dataclass
class RouterConfig:
    """Configuration for the provider router."""

    # Complexity thresholds (0.0 to 1.0)
    low_complexity_threshold: float = 0.3
    high_complexity_threshold: float = 0.7

    # Provider assignment by complexity
    low_complexity_providers: List[str] = field(default_factory=lambda: ["local"])
    medium_complexity_providers: List[str] = field(default_factory=lambda: ["local", "perplexity"])
    high_complexity_providers: List[str] = field(default_factory=lambda: ["claude", "perplexity"])
    search_providers: List[str] = field(default_factory=lambda: ["perplexity"])

    # Health check settings
    health_check_interval_seconds: int = 30
    max_consecutive_failures: int = 3
    default_unhealthy_duration_seconds: int = 60

    # Complexity estimation weights
    length_weight: float = 0.3
    keyword_weight: float = 0.4
    tool_weight: float = 0.3


class ProviderRouter:
    """
    Dynamic provider selection with fallback chains.

    Responsibilities:
    - Estimate query complexity
    - Select appropriate provider based on complexity and availability
    - Manage fallback chains for resilience
    - Track provider health and performance
    """

    # Default fallback chain: prefer local, then perplexity, then claude
    FALLBACK_CHAIN = ["local", "perplexity", "claude"]

    # Keywords that indicate higher complexity
    COMPLEX_KEYWORDS = {
        "analyze", "compare", "explain", "synthesize", "evaluate",
        "multi-step", "complex", "detailed", "comprehensive", "in-depth",
        "reasoning", "logic", "derive", "prove", "calculate",
        "architecture", "design", "implement", "refactor", "optimize",
    }

    # Keywords that indicate search is needed
    SEARCH_KEYWORDS = {
        "latest", "recent", "current", "news", "update", "today",
        "search", "find", "look up", "what is", "who is", "when did",
        "price", "stock", "weather", "score", "result",
    }

    # Keywords that indicate tool usage might be needed
    TOOL_KEYWORDS = {
        "code", "execute", "run", "file", "create", "write", "read",
        "database", "api", "query", "fetch", "send", "email",
        "calculate", "compute", "convert", "transform",
    }

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize the provider router.

        Args:
            config: Optional configuration dictionary. If not provided,
                   uses default RouterConfig settings.
        """
        # Parse config into RouterConfig
        if config:
            self.config = RouterConfig(
                low_complexity_threshold=config.get("low_complexity_threshold", 0.3),
                high_complexity_threshold=config.get("high_complexity_threshold", 0.7),
                low_complexity_providers=config.get("low_complexity_providers", ["local"]),
                medium_complexity_providers=config.get("medium_complexity_providers", ["local", "perplexity"]),
                high_complexity_providers=config.get("high_complexity_providers", ["claude", "perplexity"]),
                search_providers=config.get("search_providers", ["perplexity"]),
                health_check_interval_seconds=config.get("health_check_interval_seconds", 30),
                max_consecutive_failures=config.get("max_consecutive_failures", 3),
                default_unhealthy_duration_seconds=config.get("default_unhealthy_duration_seconds", 60),
            )
        else:
            self.config = RouterConfig()

        # Provider health tracking
        self._provider_health: Dict[str, ProviderHealth] = {}

        # Provider name to ProviderType mapping
        self._provider_type_map = {
            "local": ProviderType.LOCAL,
            "perplexity": ProviderType.PERPLEXITY,
            "claude": ProviderType.ANTHROPIC,
            "anthropic": ProviderType.ANTHROPIC,
            "openai": ProviderType.OPENAI,
            "nvidia": ProviderType.OPENAI,
        }

        # Initialize health tracking for all known providers
        for provider_name in self.FALLBACK_CHAIN:
            self._provider_health[provider_name] = ProviderHealth(
                provider_name=provider_name
            )

        # Ensure providers are set up
        self._setup_providers()

        logger.info(f"ProviderRouter initialized with fallback chain: {self.FALLBACK_CHAIN}")

    def _setup_providers(self) -> None:
        """Set up and register all available providers."""
        try:
            setup_providers()
            logger.info("Providers registered successfully")
        except Exception as e:
            logger.warning(f"Error during provider setup: {e}")

    def select_provider(self, query: str, context: Optional[Dict] = None) -> str:
        """
        Select the most appropriate provider for a query.

        Uses complexity estimation and provider availability to choose
        the best provider. Falls back through the chain if preferred
        provider is unavailable.

        Args:
            query: The user's query text
            context: Optional context dictionary with additional info:
                - "require_tools": bool - Whether tools are required
                - "require_search": bool - Whether real-time search is needed
                - "preferred_provider": str - User's preferred provider
                - "max_tokens": int - Maximum tokens needed

        Returns:
            Name of the selected provider ("local", "perplexity", or "claude")
        """
        context = context or {}

        # Check for explicit provider preference
        preferred = context.get("preferred_provider")
        if preferred and self._is_provider_available(preferred):
            logger.debug(f"Using preferred provider: {preferred}")
            return preferred

        # Check for search requirement
        if context.get("require_search") or self._requires_search(query):
            provider = self._select_from_list(self.config.search_providers)
            if provider:
                logger.debug(f"Selected search provider: {provider}")
                return provider

        # Estimate complexity
        complexity = self._estimate_complexity(query, context)
        complexity_level = self._get_complexity_level(complexity)

        logger.debug(f"Query complexity: {complexity:.2f} ({complexity_level.value})")

        # Select provider based on complexity
        if complexity_level == ComplexityLevel.LOW:
            candidates = self.config.low_complexity_providers
        elif complexity_level == ComplexityLevel.HIGH:
            candidates = self.config.high_complexity_providers
        else:
            candidates = self.config.medium_complexity_providers

        # Find first available provider from candidates
        provider = self._select_from_list(candidates)
        if provider:
            logger.info(f"Selected provider '{provider}' for complexity level {complexity_level.value}")
            return provider

        # Fall back through the default chain
        fallback = self._get_first_available_fallback()
        if fallback:
            logger.warning(f"Using fallback provider: {fallback}")
            return fallback

        # Last resort - return first in chain even if unhealthy
        logger.error("All providers unavailable, returning first in chain")
        return self.FALLBACK_CHAIN[0]

    def _estimate_complexity(self, query: str, context: Optional[Dict] = None) -> float:
        """
        Estimate the complexity of a query on a scale of 0.0 to 1.0.

        Uses multiple heuristics:
        - Query length
        - Presence of complexity keywords
        - Tool requirements from context

        Args:
            query: The query text to analyze
            context: Optional context with additional signals

        Returns:
            Complexity score between 0.0 (simple) and 1.0 (complex)
        """
        context = context or {}
        query_lower = query.lower()

        # Length-based complexity (0.0 to 1.0)
        # Queries over 500 chars are considered complex
        length_score = min(len(query) / 500.0, 1.0)

        # Keyword-based complexity (0.0 to 1.0)
        complex_count = sum(1 for kw in self.COMPLEX_KEYWORDS if kw in query_lower)
        keyword_score = min(complex_count / 5.0, 1.0)

        # Tool requirement complexity (0.0 to 1.0)
        tool_score = 0.0
        if context.get("require_tools"):
            tool_score = 0.8
        else:
            tool_count = sum(1 for kw in self.TOOL_KEYWORDS if kw in query_lower)
            tool_score = min(tool_count / 4.0, 1.0)

        # Weighted combination
        complexity = (
            self.config.length_weight * length_score +
            self.config.keyword_weight * keyword_score +
            self.config.tool_weight * tool_score
        )

        # Clamp to [0.0, 1.0]
        return max(0.0, min(1.0, complexity))

    def _requires_search(self, query: str) -> bool:
        """
        Check if query requires real-time search capabilities.

        Args:
            query: The query text to analyze

        Returns:
            True if search is likely needed
        """
        query_lower = query.lower()
        return any(kw in query_lower for kw in self.SEARCH_KEYWORDS)

    def _get_complexity_level(self, complexity: float) -> ComplexityLevel:
        """
        Convert numeric complexity to a level.

        Args:
            complexity: Numeric complexity score (0.0 to 1.0)

        Returns:
            ComplexityLevel enum value
        """
        if complexity <= self.config.low_complexity_threshold:
            return ComplexityLevel.LOW
        elif complexity >= self.config.high_complexity_threshold:
            return ComplexityLevel.HIGH
        else:
            return ComplexityLevel.MEDIUM

    def _select_from_list(self, providers: List[str]) -> Optional[str]:
        """
        Select first available provider from a list.

        Args:
            providers: List of provider names to check

        Returns:
            First available provider name, or None if all unavailable
        """
        for provider in providers:
            if self._is_provider_available(provider):
                return provider
        return None

    def _is_provider_available(self, provider: str) -> bool:
        """
        Check if a provider is available for use.

        Args:
            provider: Provider name to check

        Returns:
            True if provider is available
        """
        # Check health status
        health = self._provider_health.get(provider)
        if health and not health.is_available():
            return False

        # Verify API key is available for online providers
        if provider in ["claude", "anthropic"]:
            import os
            if not os.getenv("ANTHROPIC_API_KEY"):
                return False
        elif provider == "perplexity":
            import os
            if not os.getenv("PERPLEXITY_API_KEY"):
                return False
        elif provider == "openai":
            import os
            if not os.getenv("OPENAI_API_KEY"):
                return False

        return True

    def _get_first_available_fallback(self) -> Optional[str]:
        """
        Get the first available provider from the fallback chain.

        Returns:
            Provider name or None if all unavailable
        """
        for provider in self.FALLBACK_CHAIN:
            if self._is_provider_available(provider):
                return provider
        return None

    def get_fallback_provider(self, failed_provider: str) -> Optional[str]:
        """
        Get the next provider in the fallback chain after a failure.

        Args:
            failed_provider: Name of the provider that failed

        Returns:
            Next available provider name, or None if at end of chain
        """
        try:
            # Find position of failed provider in chain
            if failed_provider not in self.FALLBACK_CHAIN:
                # Unknown provider, start from beginning
                return self._get_first_available_fallback()

            current_index = self.FALLBACK_CHAIN.index(failed_provider)

            # Try subsequent providers in chain
            for i in range(current_index + 1, len(self.FALLBACK_CHAIN)):
                candidate = self.FALLBACK_CHAIN[i]
                if self._is_provider_available(candidate):
                    logger.info(f"Fallback from {failed_provider} to {candidate}")
                    return candidate

            # No more providers in chain
            logger.warning(f"No fallback available after {failed_provider}")
            return None

        except Exception as e:
            logger.error(f"Error getting fallback provider: {e}")
            return None

    def mark_provider_unhealthy(
        self,
        provider: str,
        duration_seconds: Optional[int] = None
    ) -> None:
        """
        Temporarily mark a provider as unavailable.

        The provider will be excluded from selection until the duration
        expires or it is manually marked healthy again.

        Args:
            provider: Name of the provider to mark unhealthy
            duration_seconds: How long to mark unhealthy (default from config)
        """
        if duration_seconds is None:
            duration_seconds = self.config.default_unhealthy_duration_seconds

        # Get or create health record
        if provider not in self._provider_health:
            self._provider_health[provider] = ProviderHealth(
                provider_name=provider
            )

        health = self._provider_health[provider]
        health.is_healthy = False
        health.unhealthy_until = time.time() + duration_seconds
        health.consecutive_failures += 1

        logger.warning(
            f"Provider {provider} marked unhealthy for {duration_seconds}s "
            f"(consecutive failures: {health.consecutive_failures})"
        )

    def mark_provider_healthy(self, provider: str) -> None:
        """
        Manually mark a provider as healthy.

        Args:
            provider: Name of the provider to mark healthy
        """
        if provider in self._provider_health:
            health = self._provider_health[provider]
            health.is_healthy = True
            health.unhealthy_until = 0.0
            health.consecutive_failures = 0
            logger.info(f"Provider {provider} manually marked healthy")

    def record_request(
        self,
        provider: str,
        success: bool,
        latency_ms: float
    ) -> None:
        """
        Record a request result for tracking provider performance.

        Args:
            provider: Name of the provider
            success: Whether the request succeeded
            latency_ms: Request latency in milliseconds
        """
        if provider not in self._provider_health:
            self._provider_health[provider] = ProviderHealth(
                provider_name=provider
            )

        health = self._provider_health[provider]
        health.total_requests += 1

        if success:
            health.successful_requests += 1
            health.consecutive_failures = 0

            # Update average latency with exponential moving average
            if health.average_latency_ms == 0:
                health.average_latency_ms = latency_ms
            else:
                alpha = 0.2  # Smoothing factor
                health.average_latency_ms = (
                    alpha * latency_ms +
                    (1 - alpha) * health.average_latency_ms
                )
        else:
            health.consecutive_failures += 1

            # Auto-mark unhealthy after max consecutive failures
            if health.consecutive_failures >= self.config.max_consecutive_failures:
                self.mark_provider_unhealthy(provider)

    def get_provider_instance(self, provider_name: str) -> Optional[BaseProvider]:
        """
        Get a provider instance for the given provider name.

        Args:
            provider_name: Name of the provider ("local", "perplexity", "claude")

        Returns:
            BaseProvider instance or None if not available
        """
        try:
            registry = get_registry()

            # Map provider name to type
            provider_type = self._provider_type_map.get(provider_name)
            if not provider_type:
                logger.error(f"Unknown provider: {provider_name}")
                return None

            # Load config for this provider
            configs = ProviderConfigLoader.load_all_configs()
            config_key = provider_name if provider_name != "claude" else "anthropic"

            if config_key not in configs:
                logger.error(f"No config found for provider: {provider_name}")
                return None

            config = configs[config_key]

            # Get or create provider instance
            return registry.get_provider(config, name=provider_name)

        except Exception as e:
            logger.error(f"Error getting provider instance for {provider_name}: {e}")
            return None

    def get_health_status(self) -> Dict[str, Dict]:
        """
        Get health status for all tracked providers.

        Returns:
            Dictionary with provider health information
        """
        status = {}
        for name, health in self._provider_health.items():
            status[name] = {
                "is_healthy": health.is_healthy,
                "is_available": health.is_available(),
                "consecutive_failures": health.consecutive_failures,
                "total_requests": health.total_requests,
                "success_rate": health.success_rate,
                "average_latency_ms": round(health.average_latency_ms, 2),
            }
        return status

    def get_routing_summary(self) -> Dict:
        """
        Get a summary of routing configuration and status.

        Returns:
            Dictionary with routing configuration and health status
        """
        return {
            "fallback_chain": self.FALLBACK_CHAIN,
            "complexity_thresholds": {
                "low": self.config.low_complexity_threshold,
                "high": self.config.high_complexity_threshold,
            },
            "provider_assignments": {
                "low_complexity": self.config.low_complexity_providers,
                "medium_complexity": self.config.medium_complexity_providers,
                "high_complexity": self.config.high_complexity_providers,
                "search": self.config.search_providers,
            },
            "provider_health": self.get_health_status(),
        }


# Convenience functions for module-level access

_default_router: Optional[ProviderRouter] = None


def get_router(config: Optional[Dict] = None) -> ProviderRouter:
    """
    Get the default provider router instance.

    Args:
        config: Optional configuration (only used for first call)

    Returns:
        ProviderRouter singleton instance
    """
    global _default_router
    if _default_router is None:
        _default_router = ProviderRouter(config)
    return _default_router


def select_provider(query: str, context: Optional[Dict] = None) -> str:
    """
    Select a provider for the given query using the default router.

    Args:
        query: The user's query text
        context: Optional context dictionary

    Returns:
        Name of the selected provider
    """
    return get_router().select_provider(query, context)


def get_fallback(failed_provider: str) -> Optional[str]:
    """
    Get fallback provider after a failure using the default router.

    Args:
        failed_provider: Name of the provider that failed

    Returns:
        Next available provider name, or None
    """
    return get_router().get_fallback_provider(failed_provider)
