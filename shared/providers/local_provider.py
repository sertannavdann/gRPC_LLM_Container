"""Local LLM provider wrapping llama.cpp via gRPC."""

import logging
from typing import List, AsyncIterator
from .base_provider import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ModelInfo,
    ChatRequest,
    ChatResponse,
    ProviderConnectionError,
)
from shared.clients.llm_client import LLMClient

logger = logging.getLogger(__name__)


class LocalProvider(BaseProvider):
    """
    Provider for local LLM inference via llama.cpp and gRPC.

    Wraps the existing LLMClient to provide a standard provider interface.
    """

    def __init__(
        self,
        config: ProviderConfig,
        llm_client=None,
        host: str = "llm_service",
        port: int = 50051,
    ):
        """
        Initialize LocalProvider.

        Args:
            config: ProviderConfig with provider settings
            llm_client: Optional existing LLMClient instance
            host: gRPC host for LLM service (default: llm_service)
            port: gRPC port for LLM service (default: 50051)
        """
        super().__init__(config)
        if llm_client is not None:
            self.llm_client = llm_client
        else:
            self.llm_client = LLMClient(host=host, port=port)
        self._available_models: List[ModelInfo] = []
        logger.info(f"LocalProvider initialized with gRPC endpoint {host}:{port}")

    async def generate(self, request: ChatRequest) -> ChatResponse:
        """
        Generate a completion using local LLM.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            ChatResponse with model output

        Raises:
            ProviderConnectionError: If LLM service is unavailable
        """
        try:
            # Convert messages to prompt format
            prompt = self._format_messages(request.messages)

            # Call synchronous LLMClient.generate
            content = self.llm_client.generate(
                prompt=prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            )

            return ChatResponse(
                model=request.model,
                content=content,
                stop_reason="stop",
                usage={
                    "prompt_tokens": len(prompt.split()),
                    "completion_tokens": len(content.split()),
                },
                raw_response=None,
            )
        except Exception as e:
            logger.error(f"Local LLM generation failed: {str(e)}")
            raise ProviderConnectionError(f"Local LLM generation failed: {str(e)}")

    async def generate_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Generate a streaming completion using local LLM.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            String tokens as they become available

        Raises:
            ProviderConnectionError: If LLM service is unavailable
        """
        try:
            prompt = self._format_messages(request.messages)

            # Use synchronous streaming client
            for response in self.llm_client.generate_stream(
                prompt=prompt,
                max_tokens=request.max_tokens,
                temperature=request.temperature,
            ):
                yield response.token
                if response.is_final:
                    break

        except Exception as e:
            logger.error(f"Local LLM streaming failed: {str(e)}")
            raise ProviderConnectionError(f"Local LLM streaming failed: {str(e)}")

    async def get_models(self) -> List[ModelInfo]:
        """
        Get list of available local models.

        Returns:
            List of ModelInfo instances
        """
        # For local provider, we return a single model entry
        # The actual model is determined by what's loaded in llama.cpp
        if not self._available_models:
            self._available_models = [
                ModelInfo(
                    name="local-llm",
                    description="Local LLM inference via llama.cpp",
                    supports_streaming=True,
                    supports_function_calling=True,
                    context_window=4096,
                    max_tokens=2048,
                )
            ]
        return self._available_models

    async def health_check(self) -> bool:
        """
        Check if local LLM service is accessible.

        Returns:
            True if service is healthy, False otherwise
        """
        try:
            # Try a simple generation to verify service is working
            response = self.llm_client.generate(
                prompt="Health check",
                max_tokens=10,
                temperature=0.7,
            )
            is_healthy = bool(response and not response.startswith("LLM Service Error"))
            return is_healthy
        except Exception as e:
            logger.warning(f"Health check failed: {str(e)}")
            return False

    def _format_messages(self, messages) -> str:
        """
        Format chat messages into a single prompt string.

        Args:
            messages: List of ChatMessage objects or dicts with 'role' and 'content'

        Returns:
            Formatted prompt string
        """
        prompt_parts = []

        for msg in messages:
            # Handle both ChatMessage objects and dicts
            if hasattr(msg, "role"):
                role = msg.role
                content = msg.content
            else:
                role = msg.get("role", "user")
                content = msg.get("content", "")

            if role == "system":
                prompt_parts.append(f"System: {content}")
            elif role == "user":
                prompt_parts.append(f"User: {content}")
            elif role == "assistant":
                prompt_parts.append(f"Assistant: {content}")

        return "\n".join(prompt_parts)
