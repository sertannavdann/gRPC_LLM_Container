"""OpenAI provider using standard OpenAI API."""

import logging
from typing import List
from .online_provider import OnlineProvider
from .base_provider import ProviderConfig, ModelInfo

logger = logging.getLogger(__name__)


class OpenAIProvider(OnlineProvider):
    """
    Provider for OpenAI models (GPT-4, o3, etc).

    Uses OpenAI's native API endpoint at https://api.openai.com/v1
    """

    # Default OpenAI models
    OPENAI_MODELS = [
        ModelInfo(
            name="o3",
            description="OpenAI o3 - Reasoning model",
            supports_streaming=False,
            supports_function_calling=True,
            context_window=200000,
            max_tokens=100000,
        ),
        ModelInfo(
            name="gpt-4o",
            description="GPT-4o - Multimodal flagship",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="gpt-4-turbo",
            description="GPT-4 Turbo",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=4096,
        ),
        ModelInfo(
            name="gpt-4",
            description="GPT-4",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=8192,
            max_tokens=2048,
        ),
        ModelInfo(
            name="gpt-3.5-turbo",
            description="GPT-3.5 Turbo",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=4096,
            max_tokens=2048,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        """
        Initialize OpenAIProvider.

        Args:
            config: ProviderConfig with OpenAI API settings
        """
        # Default to OpenAI's official endpoint
        base_url = config.base_url or "https://api.openai.com/v1"

        super().__init__(
            config=config,
            base_url=base_url,
            api_key=config.api_key,
        )
        self.name = "openai"
        logger.info(f"OpenAIProvider initialized with base_url: {base_url}")

    def _get_default_models(self) -> List[ModelInfo]:
        """
        Get default list of OpenAI models.

        Returns:
            List of available OpenAI models
        """
        return self.OPENAI_MODELS
