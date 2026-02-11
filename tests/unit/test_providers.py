"""Unit tests for provider abstraction layer."""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from shared.providers import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    LocalProvider,
    AnthropicProvider,
    OpenAIProvider,
    PerplexityProvider,
    ProviderRegistry,
    ChatMessage,
    ChatRequest,
    ModelInfo,
    setup_providers,
)


class TestProviderConfig:
    """Tests for ProviderConfig."""

    def test_local_config(self):
        """Test creating a local provider config."""
        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        assert config.provider_type == ProviderType.LOCAL
        assert config.timeout == 30

    def test_anthropic_config(self):
        """Test creating an Anthropic provider config."""
        config = ProviderConfig(
            provider_type=ProviderType.ANTHROPIC,
            api_key="test-key",
        )
        assert config.provider_type == ProviderType.ANTHROPIC
        assert config.api_key == "test-key"


class TestLocalProvider:
    """Tests for LocalProvider."""

    def test_local_provider_init(self):
        """Test LocalProvider initialization."""
        config = ProviderConfig(provider_type=ProviderType.LOCAL)

        # Mock the LLMClient
        mock_client = Mock()
        provider = LocalProvider(config, llm_client=mock_client)

        assert provider.name == "local"
        assert provider.llm_client == mock_client

    @pytest.mark.asyncio
    async def test_local_provider_get_models(self):
        """Test getting models from LocalProvider."""
        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        mock_client = Mock()
        provider = LocalProvider(config, llm_client=mock_client)

        models = await provider.get_models()
        assert len(models) > 0
        assert models[0].name == "local-llm"

    @pytest.mark.asyncio
    async def test_local_provider_health_check(self):
        """Test health check for LocalProvider."""
        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        mock_client = Mock()
        mock_client.generate.return_value = "OK"
        provider = LocalProvider(config, llm_client=mock_client)

        result = await provider.health_check()
        assert result is True

    @pytest.mark.asyncio
    async def test_local_provider_health_check_failure(self):
        """Test health check failure for LocalProvider."""
        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        mock_client = Mock()
        mock_client.generate.side_effect = Exception("Connection failed")
        provider = LocalProvider(config, llm_client=mock_client)

        result = await provider.health_check()
        assert result is False


class TestProviderRegistry:
    """Tests for ProviderRegistry."""

    def test_registry_register(self):
        """Test registering a provider."""
        registry = ProviderRegistry()
        registry.register(ProviderType.LOCAL, LocalProvider)

        assert ProviderType.LOCAL in registry._providers

    def test_registry_list_available(self):
        """Test listing available providers."""
        registry = ProviderRegistry()
        registry.register(ProviderType.LOCAL, LocalProvider)
        registry.register(ProviderType.ANTHROPIC, AnthropicProvider)

        available = registry.list_available()
        assert "local" in available
        assert "anthropic" in available

    def test_registry_get_provider(self):
        """Test getting a provider from registry."""
        registry = ProviderRegistry()
        registry.register(ProviderType.LOCAL, LocalProvider)

        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        provider = registry.get_provider(config)

        assert isinstance(provider, LocalProvider)

    def test_registry_set_default(self):
        """Test setting default provider."""
        registry = ProviderRegistry()
        registry.register(ProviderType.LOCAL, LocalProvider)

        config = ProviderConfig(provider_type=ProviderType.LOCAL)
        provider = registry.get_provider(config, name="default")
        registry.set_default("default")

        assert registry.get_default() == provider


class TestProviderTypes:
    """Tests for different provider types."""

    def test_anthropic_provider_init(self):
        """Test AnthropicProvider initialization."""
        config = ProviderConfig(
            provider_type=ProviderType.ANTHROPIC,
            api_key="test-key",
        )
        provider = AnthropicProvider(config)
        assert provider.name == "claude"

    @pytest.mark.asyncio
    async def test_anthropic_provider_get_models(self):
        """Test getting Claude models."""
        config = ProviderConfig(
            provider_type=ProviderType.ANTHROPIC,
            api_key="test-key",
        )
        provider = AnthropicProvider(config)
        models = await provider.get_models()

        assert len(models) > 0
        assert any("claude" in m.name for m in models)

    def test_openai_provider_init(self):
        """Test OpenAIProvider initialization."""
        config = ProviderConfig(
            provider_type=ProviderType.OPENAI,
            api_key="test-key",
        )
        provider = OpenAIProvider(config)
        assert provider.name == "openai"

    @pytest.mark.asyncio
    async def test_openai_provider_get_models(self):
        """Test getting OpenAI models."""
        config = ProviderConfig(
            provider_type=ProviderType.OPENAI,
            api_key="test-key",
        )
        provider = OpenAIProvider(config)
        models = await provider.get_models()

        assert len(models) > 0
        assert any("gpt" in m.name for m in models)

    def test_perplexity_provider_init(self):
        """Test PerplexityProvider initialization."""
        config = ProviderConfig(
            provider_type=ProviderType.PERPLEXITY,
            api_key="test-key",
        )
        provider = PerplexityProvider(config)
        assert provider.name == "perplexity"

    @pytest.mark.asyncio
    async def test_perplexity_provider_get_models(self):
        """Test getting Perplexity models."""
        config = ProviderConfig(
            provider_type=ProviderType.PERPLEXITY,
            api_key="test-key",
        )
        provider = PerplexityProvider(config)
        models = await provider.get_models()

        assert len(models) > 0
        assert any("sonar" in m.name for m in models)


class TestSetupProviders:
    """Tests for provider setup."""

    def test_setup_providers(self):
        """Test that setup_providers registers all providers."""
        from shared.providers.registry import _global_registry

        # Clear existing registrations
        _global_registry._providers.clear()

        setup_providers()

        available = _global_registry.list_available()
        assert "local" in available
        assert "anthropic" in available
        assert "openai" in available
        assert "perplexity" in available
