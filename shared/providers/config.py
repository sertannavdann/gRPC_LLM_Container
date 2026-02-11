"""Provider configuration loading and management."""

import os
import logging
from typing import Dict, Optional
from .base_provider import ProviderConfig, ProviderType

logger = logging.getLogger(__name__)


class ProviderConfigLoader:
    """Load provider configurations from environment variables."""

    @staticmethod
    def load_local_config() -> ProviderConfig:
        """
        Load configuration for local provider.

        Returns:
            ProviderConfig for local LLM service
        """
        return ProviderConfig(
            provider_type=ProviderType.LOCAL,
            extra={
                "host": os.getenv("LLM_SERVICE_HOST", "llm_service"),
                "port": int(os.getenv("LLM_SERVICE_PORT", "50051")),
            },
        )

    @staticmethod
    def load_anthropic_config() -> ProviderConfig:
        """
        Load configuration for Anthropic/Claude provider.

        Expects ANTHROPIC_API_KEY environment variable.

        Returns:
            ProviderConfig for Claude API
        """
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.warning("ANTHROPIC_API_KEY not set")

        return ProviderConfig(
            provider_type=ProviderType.ANTHROPIC,
            api_key=api_key,
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.anthropic.com/v1"),
            timeout=int(os.getenv("ANTHROPIC_TIMEOUT", "30")),
        )

    @staticmethod
    def load_openai_config() -> ProviderConfig:
        """
        Load configuration for OpenAI provider.

        Expects OPENAI_API_KEY environment variable.

        Returns:
            ProviderConfig for OpenAI API
        """
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            logger.warning("OPENAI_API_KEY not set")

        return ProviderConfig(
            provider_type=ProviderType.OPENAI,
            api_key=api_key,
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            timeout=int(os.getenv("OPENAI_TIMEOUT", "30")),
        )

    @staticmethod
    def load_perplexity_config() -> ProviderConfig:
        """
        Load configuration for Perplexity provider.

        Expects PERPLEXITY_API_KEY environment variable.

        Returns:
            ProviderConfig for Perplexity API
        """
        api_key = os.getenv("PERPLEXITY_API_KEY")
        if not api_key:
            logger.warning("PERPLEXITY_API_KEY not set")

        return ProviderConfig(
            provider_type=ProviderType.PERPLEXITY,
            api_key=api_key,
            base_url=os.getenv("PERPLEXITY_BASE_URL", "https://api.perplexity.ai"),
            timeout=int(os.getenv("PERPLEXITY_TIMEOUT", "30")),
        )

    @staticmethod
    def load_all_configs() -> Dict[str, ProviderConfig]:
        """
        Load all provider configurations from environment.

        Returns:
            Dictionary mapping provider names to ProviderConfig instances
        """
        return {
            "local": ProviderConfigLoader.load_local_config(),
            "anthropic": ProviderConfigLoader.load_anthropic_config(),
            "openai": ProviderConfigLoader.load_openai_config(),
            "perplexity": ProviderConfigLoader.load_perplexity_config(),
        }
