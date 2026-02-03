"""Provider setup and initialization."""

import logging
from .base_provider import ProviderType
from .registry import get_registry
from .local_provider import LocalProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .perplexity_provider import PerplexityProvider
from .openclaw_provider import OpenClawProvider

logger = logging.getLogger(__name__)


def setup_providers() -> None:
    """
    Register all available providers in the global registry.

    Call this once at application startup to enable provider usage.
    """
    registry = get_registry()

    # Register local provider
    registry.register(ProviderType.LOCAL, LocalProvider)
    logger.info("Registered LocalProvider")

    # Register online providers
    registry.register(ProviderType.ANTHROPIC, AnthropicProvider)
    logger.info("Registered AnthropicProvider")

    registry.register(ProviderType.OPENAI, OpenAIProvider)
    logger.info("Registered OpenAIProvider")

    registry.register(ProviderType.PERPLEXITY, PerplexityProvider)
    logger.info("Registered PerplexityProvider")

    # Register OpenClaw gateway provider
    registry.register(ProviderType.OPENCLAW, OpenClawProvider)
    logger.info("Registered OpenClawProvider")

    logger.info(f"Available providers: {registry.list_available()}")
