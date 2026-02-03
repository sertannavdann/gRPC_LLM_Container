"""OpenClaw Gateway provider using OpenAI-compatible API."""

import logging
from typing import List
from .online_provider import OnlineProvider
from .base_provider import ProviderConfig, ModelInfo

logger = logging.getLogger(__name__)


class OpenClawProvider(OnlineProvider):
    """
    Provider for OpenClaw Gateway which proxies to various LLM backends.
    
    OpenClaw provides an OpenAI-compatible API that routes requests to:
    - GitHub Copilot proxy (gpt-5.2, gpt-5.1)
    - Claude web interface
    - OpenAI API
    - Local models
    
    Default endpoint: http://openclaw-gateway:18789/v1 (Docker network)
    or http://localhost:18789/v1 (host network)
    """

    # OpenClaw models (via copilot-proxy)
    OPENCLAW_MODELS = [
        ModelInfo(
            name="gpt-5.2",
            description="GPT-5.2 via Copilot proxy",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=8192,
        ),
        ModelInfo(
            name="gpt-5.2-codex",
            description="GPT-5.2 Codex for code tasks",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=8192,
        ),
        ModelInfo(
            name="gpt-5.1",
            description="GPT-5.1 via Copilot proxy",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=8192,
        ),
        ModelInfo(
            name="gpt-5.1-codex",
            description="GPT-5.1 Codex for code tasks",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=8192,
        ),
        ModelInfo(
            name="gpt-5.1-codex-max",
            description="GPT-5.1 Codex Max for complex tasks",
            supports_streaming=True,
            supports_function_calling=True,
            context_window=128000,
            max_tokens=16384,
        ),
    ]

    def __init__(self, config: ProviderConfig):
        """
        Initialize OpenClawProvider.

        Args:
            config: ProviderConfig with OpenClaw gateway settings
        """
        # Default to OpenClaw gateway endpoint
        # Use host.docker.internal when running in Docker, localhost otherwise
        base_url = config.base_url or "http://host.docker.internal:18789/v1"
        
        # OpenClaw may not require API key depending on auth mode
        api_key = config.api_key or "openclaw"

        super().__init__(
            config=config,
            base_url=base_url,
            api_key=api_key,
        )
        self.name = "openclaw"
        logger.info(f"OpenClawProvider initialized with base_url: {base_url}")

    def _get_default_models(self) -> List[ModelInfo]:
        """
        Get default list of OpenClaw models.

        Returns:
            List of available OpenClaw models via gateway
        """
        return self.OPENCLAW_MODELS

    def _get_headers(self) -> dict:
        """
        Get headers for API requests.
        
        OpenClaw may use token auth instead of bearer token.
        """
        headers = {
            "Content-Type": "application/json",
        }
        
        # Only add auth header if we have a real API key
        if self.api_key and self.api_key != "openclaw":
            headers["Authorization"] = f"Bearer {self.api_key}"
        
        return headers
