"""Provider abstraction layer for multi-LLM support."""

from .base_provider import (
    BaseProvider,
    ProviderConfig,
    ProviderError,
    ProviderType,
    ModelInfo,
    ChatMessage,
    ChatRequest,
    ChatResponse,
)
from .registry import ProviderRegistry, get_registry, get_provider, register_provider
from .setup import setup_providers
from .config import ProviderConfigLoader
from .local_provider import LocalProvider
from .online_provider import OnlineProvider
from .anthropic_provider import AnthropicProvider
from .openai_provider import OpenAIProvider
from .perplexity_provider import PerplexityProvider
from .openclaw_provider import OpenClawProvider
from .github_models import GitHubModelsProvider

__all__ = [
    # Base classes
    "BaseProvider",
    "OnlineProvider",
    # Configuration and types
    "ProviderConfig",
    "ProviderType",
    "ModelInfo",
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    # Error types
    "ProviderError",
    # Registry
    "ProviderRegistry",
    "get_registry",
    "get_provider",
    "register_provider",
    # Setup
    "setup_providers",
    # Implementations
    "LocalProvider",
    "AnthropicProvider",
    "OpenAIProvider",
    "PerplexityProvider",
    "OpenClawProvider",
    "GitHubModelsProvider",
    # Config
    "ProviderConfigLoader",
]

