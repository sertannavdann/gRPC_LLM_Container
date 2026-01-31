"""Abstract base class for all LLM providers."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import AsyncIterator, Iterator, Optional, List, Dict, Any
from enum import Enum


class ProviderType(str, Enum):
    """Enumeration of provider types."""
    LOCAL = "local"
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"
    PERPLEXITY = "perplexity"
    OLLAMA = "ollama"


@dataclass
class ProviderConfig:
    """Configuration for a provider."""
    provider_type: ProviderType
    api_key: Optional[str] = None
    base_url: Optional[str] = None
    timeout: int = 30
    max_retries: int = 3
    extra: Dict[str, Any] = field(default_factory=dict)


class ProviderError(Exception):
    """Base exception for provider errors."""
    pass


class ProviderConnectionError(ProviderError):
    """Raised when unable to connect to provider."""
    pass


class ProviderAuthError(ProviderError):
    """Raised when authentication fails."""
    pass


class ProviderRateLimitError(ProviderError):
    """Raised when rate limited by provider."""
    pass


@dataclass
class ModelInfo:
    """Information about an available model."""
    name: str
    description: Optional[str] = None
    supports_streaming: bool = True
    supports_function_calling: bool = True
    context_window: Optional[int] = None
    max_tokens: Optional[int] = None


@dataclass
class ChatMessage:
    """A message in a chat conversation."""
    role: str  # "user", "assistant", "system"
    content: str


@dataclass
class ChatRequest:
    """Request for chat completion."""
    messages: List[ChatMessage]
    model: str
    temperature: float = 0.7
    max_tokens: int = 2048
    top_p: float = 1.0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    stream: bool = False
    tools: Optional[List[Dict[str, Any]]] = None
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResponse:
    """Response from chat completion."""
    model: str
    content: str
    stop_reason: str  # "stop", "length", "tool_use", etc.
    usage: Optional[Dict[str, int]] = None  # {"prompt_tokens": N, "completion_tokens": N}
    tool_calls: Optional[List[Dict[str, Any]]] = None
    raw_response: Optional[Dict[str, Any]] = None


class BaseProvider(ABC):
    """
    Abstract base class for all LLM providers.

    Defines the interface that all providers must implement to enable
    runtime provider switching without code changes.
    """

    def __init__(self, config: ProviderConfig):
        """
        Initialize provider with configuration.

        Args:
            config: ProviderConfig instance with provider settings
        """
        self.config = config
        self.name = config.provider_type.value

    @abstractmethod
    async def generate(self, request: ChatRequest) -> ChatResponse:
        """
        Generate a single completion asynchronously.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            ChatResponse with model output

        Raises:
            ProviderError: If generation fails
        """
        pass

    @abstractmethod
    async def generate_stream(self, request: ChatRequest) -> AsyncIterator[str]:
        """
        Generate a streaming completion asynchronously.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            String tokens as they become available

        Raises:
            ProviderError: If streaming fails
        """
        pass

    def generate_sync(self, request: ChatRequest) -> ChatResponse:
        """
        Synchronous wrapper for generate().

        Provides sync interface for backward compatibility.
        Override if a more efficient sync implementation exists.

        Args:
            request: ChatRequest with messages and parameters

        Returns:
            ChatResponse with model output
        """
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self.generate(request))
        finally:
            loop.close()

    def generate_stream_sync(self, request: ChatRequest) -> Iterator[str]:
        """
        Synchronous wrapper for generate_stream().

        Provides sync interface for backward compatibility.

        Args:
            request: ChatRequest with messages and parameters

        Yields:
            String tokens as they become available
        """
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            async_gen = self.generate_stream(request)
            while True:
                try:
                    token = loop.run_until_complete(async_gen.__anext__())
                    yield token
                except StopAsyncIteration:
                    break
        finally:
            loop.close()

    @abstractmethod
    async def get_models(self) -> List[ModelInfo]:
        """
        Get list of available models from provider.

        Returns:
            List of ModelInfo instances

        Raises:
            ProviderError: If retrieval fails
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if provider is accessible and responding.

        Returns:
            True if provider is healthy, False otherwise
        """
        pass

    async def validate_config(self) -> bool:
        """
        Validate that provider configuration is correct.

        Default implementation calls health_check().
        Override for provider-specific validation.

        Returns:
            True if configuration is valid

        Raises:
            ProviderAuthError: If authentication fails
            ProviderConnectionError: If connection fails
        """
        try:
            return await self.health_check()
        except Exception as e:
            raise ProviderConnectionError(f"Provider validation failed: {str(e)}")
