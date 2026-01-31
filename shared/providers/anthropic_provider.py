"""Claude (Anthropic) provider using OpenAI-compatible API wrapper."""

import logging
from typing import List, Dict, Any, Optional
from .online_provider import OnlineProvider
from .base_provider import ProviderConfig, ProviderType, ModelInfo

logger = logging.getLogger(__name__)


class AnthropicProvider(OnlineProvider):
    """
    Provider for Claude via Anthropic API.

    Note: Claude API is being wrapped to support OpenAI-compatible endpoints
    via a compatibility layer or by using Claude's native API with adaptation.
    """

    # Default Claude models
    CLAUDE_MODELS = [
        ModelInfo(
            name="claude-opus-4-20250514",
            description="Claude Opus 4 - Latest flagship model",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=200000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="claude-3-5-sonnet-20241022",
            description="Claude 3.5 Sonnet",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=200000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="claude-3-sonnet-20240229",
            description="Claude 3 Sonnet",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=200000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="claude-3-haiku-20240307",
            description="Claude 3 Haiku - Fast and efficient",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=200000,
            max_tokens=1024,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        """
        Initialize AnthropicProvider.

        Args:
            config: ProviderConfig with Anthropic API settings
        """
        # Default to Anthropic's official API endpoint
        base_url = config.base_url or "https://api.anthropic.com/v1"

        super().__init__(
            config=config,
            base_url=base_url,
            api_key=config.api_key,
        )
        self.name = "claude"
        logger.info(f"AnthropicProvider initialized with base_url: {base_url}")

    def _get_default_models(self) -> List[ModelInfo]:
        """
        Get default list of Claude models.

        Returns:
            List of available Claude models
        """
        return self.CLAUDE_MODELS

    def _build_headers(self) -> Dict[str, str]:
        """
        Build HTTP headers for Anthropic API.

        Anthropic uses 'x-api-key' header instead of Authorization.

        Returns:
            Dictionary of headers
        """
        headers = {
            "Content-Type": "application/json",
        }
        if self.api_key:
            headers["x-api-key"] = self.api_key
        return headers
