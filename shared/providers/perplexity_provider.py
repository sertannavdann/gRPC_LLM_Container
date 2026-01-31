"""Perplexity Sonar provider using OpenAI-compatible API."""

import logging
from typing import List
from .online_provider import OnlineProvider
from .base_provider import ProviderConfig, ModelInfo

logger = logging.getLogger(__name__)


class PerplexityProvider(OnlineProvider):
    """
    Provider for Perplexity Sonar models.

    Uses Perplexity's OpenAI-compatible API endpoint.
    Features integrated search and reasoning capabilities.
    """

    # Perplexity Sonar models
    PERPLEXITY_MODELS = [
        ModelInfo(
            name="sonar-reasoning",
            description="Perplexity Sonar Reasoning - Advanced reasoning with search",
            supports_streaming=True,
            supports_function_calling=False,
            context_window=127000,
            max_tokens=4000,
        ),
        ModelInfo(
            name="sonar-pro",
            description="Perplexity Sonar Pro - Fast reasoning with real-time search",
            supports_streaming=True,
            supports_function_calling=False,
            context_window=200000,
            max_tokens=4000,
        ),
        ModelInfo(
            name="sonar",
            description="Perplexity Sonar - Balanced search and reasoning",
            supports_streaming=True,
            supports_function_calling=False,
            context_window=127000,
            max_tokens=4000,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        """
        Initialize PerplexityProvider.

        Args:
            config: ProviderConfig with Perplexity API settings
        """
        # Default to Perplexity's official endpoint
        base_url = config.base_url or "https://api.perplexity.ai"

        super().__init__(
            config=config,
            base_url=base_url,
            api_key=config.api_key,
        )
        self.name = "perplexity"
        logger.info(f"PerplexityProvider initialized with base_url: {base_url}")

    def _get_default_models(self) -> List[ModelInfo]:
        """
        Get default list of Perplexity Sonar models.

        Returns:
            List of available Perplexity models
        """
        return self.PERPLEXITY_MODELS
