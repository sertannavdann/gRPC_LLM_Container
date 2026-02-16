"""Unit tests for GitHub Models provider."""

import sys
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import aiohttp

# Mock llm_pb2 to avoid import errors
sys.modules['llm_service.llm_pb2'] = MagicMock()
sys.modules['llm_service.llm_pb2_grpc'] = MagicMock()

from shared.providers.github_models import GitHubModelsProvider
from shared.providers.base_provider import (
    ProviderConfig,
    ProviderType,
    ChatRequest,
    ChatMessage,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderConnectionError,
)


@pytest.fixture
def provider_config():
    """Create test provider config."""
    return ProviderConfig(
        provider_type=ProviderType.OPENAI,  # No GITHUB_MODELS enum yet
        api_key="test_github_token_12345",
        timeout=30,
        max_retries=3,
    )


@pytest.fixture
def github_provider(provider_config):
    """Create GitHub Models provider instance."""
    return GitHubModelsProvider(config=provider_config)


@pytest.fixture
def github_provider_with_org(provider_config):
    """Create GitHub Models provider with org attribution."""
    return GitHubModelsProvider(
        config=provider_config,
        org_id="my-enterprise-org"
    )


@pytest.fixture
def sample_request():
    """Create sample chat request."""
    return ChatRequest(
        messages=[
            ChatMessage(role="system", content="You are a helpful assistant."),
            ChatMessage(role="user", content="Hello!"),
        ],
        model="gpt-4o-mini",
        temperature=0.7,
        max_tokens=100,
    )


@pytest.fixture
def mock_success_response():
    """Mock successful API response."""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1677652288,
        "model": "gpt-4o-mini",
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": "Hello! How can I help you today?",
                },
                "finish_reason": "stop",
            }
        ],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 9,
            "total_tokens": 19,
        },
    }


class TestGitHubModelsProvider:
    """Test suite for GitHubModelsProvider."""

    def test_initialization(self, github_provider):
        """Test provider initialization."""
        assert github_provider.name == "github_models"
        assert github_provider.api_key == "test_github_token_12345"
        assert github_provider.base_url == GitHubModelsProvider.DEFAULT_BASE_URL
        assert github_provider.org_id is None

    def test_initialization_with_org(self, github_provider_with_org):
        """Test provider initialization with org attribution."""
        assert github_provider_with_org.org_id == "my-enterprise-org"

    def test_build_headers(self, github_provider):
        """Test header construction."""
        headers = github_provider._build_headers()

        assert headers["Authorization"] == "Bearer test_github_token_12345"
        assert headers["X-GitHub-Api-Version"] == GitHubModelsProvider.API_VERSION
        assert headers["Accept"] == "application/json"
        assert headers["Content-Type"] == "application/json"

    def test_build_endpoint_without_org(self, github_provider):
        """Test endpoint URL without org attribution."""
        url = github_provider._build_endpoint()
        assert url == f"{GitHubModelsProvider.DEFAULT_BASE_URL}/chat/completions"

    def test_build_endpoint_with_org(self, github_provider_with_org):
        """Test endpoint URL with org attribution."""
        url = github_provider_with_org._build_endpoint()
        expected = f"{GitHubModelsProvider.DEFAULT_BASE_URL}/orgs/my-enterprise-org/chat/completions"
        assert url == expected

    def test_build_payload_basic(self, github_provider, sample_request):
        """Test basic payload construction."""
        payload = github_provider._build_payload(sample_request)

        assert payload["model"] == "gpt-4o-mini"
        assert payload["temperature"] == 0.7
        assert payload["max_tokens"] == 100
        assert len(payload["messages"]) == 2
        assert payload["messages"][0]["role"] == "system"
        assert payload["messages"][1]["content"] == "Hello!"

    def test_build_payload_with_response_format(self, github_provider, sample_request):
        """Test payload with structured output schema."""
        schema = {
            "type": "json_schema",
            "json_schema": {
                "name": "test_output",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {"result": {"type": "string"}},
                    "required": ["result"],
                },
            },
        }

        payload = github_provider._build_payload(sample_request, response_format=schema)
        assert payload["response_format"] == schema

    def test_build_payload_with_seed(self, github_provider, sample_request):
        """Test payload with seed for reproducibility."""
        sample_request.extra = {"seed": 42}
        payload = github_provider._build_payload(sample_request)

        assert payload["seed"] == 42

    def test_parse_response(self, github_provider, mock_success_response):
        """Test response parsing."""
        response = github_provider._parse_response(mock_success_response, "gpt-4o-mini")

        assert response.model == "gpt-4o-mini"
        assert response.content == "Hello! How can I help you today?"
        assert response.stop_reason == "stop"
        assert response.usage["prompt_tokens"] == 10
        assert response.usage["completion_tokens"] == 9

    @pytest.mark.asyncio
    async def test_generate_success(
        self, github_provider, sample_request, mock_success_response
    ):
        """Test successful generation."""
        # Mock aiohttp response
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.json = AsyncMock(return_value=mock_success_response)
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        # Mock session
        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        # Patch the session creation
        github_provider._session = mock_session

        # Execute
        response = await github_provider.generate(sample_request)

        # Verify
        assert response.content == "Hello! How can I help you today?"
        assert response.model == "gpt-4o-mini"

        # Clean up
        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_auth_error(self, github_provider, sample_request):
        """Test generation with auth error (no retry)."""
        # Mock 401 response
        mock_response = AsyncMock()
        mock_response.status = 401
        mock_response.text = AsyncMock(return_value="Invalid API key")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        github_provider._session = mock_session

        # Should raise auth error without retry
        with pytest.raises(ProviderAuthError, match="Authentication failed"):
            await github_provider.generate(sample_request)

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_rate_limit_retry_success(
        self, github_provider, sample_request, mock_success_response
    ):
        """Test rate limit with successful retry."""
        # First call: 429, second call: 200
        mock_response_429 = AsyncMock()
        mock_response_429.status = 429
        mock_response_429.text = AsyncMock(return_value="Rate limited")
        mock_response_429.__aenter__ = AsyncMock(return_value=mock_response_429)
        mock_response_429.__aexit__ = AsyncMock(return_value=None)

        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json = AsyncMock(return_value=mock_success_response)
        mock_response_200.__aenter__ = AsyncMock(return_value=mock_response_200)
        mock_response_200.__aexit__ = AsyncMock(return_value=None)

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_429
            return mock_response_200

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=mock_post)
        mock_session.closed = False

        github_provider._session = mock_session

        # Reduce delay for test speed
        github_provider.INITIAL_RETRY_DELAY = 0.01

        # Execute
        response = await github_provider.generate(sample_request)

        # Verify retry happened and succeeded
        assert call_count == 2
        assert response.content == "Hello! How can I help you today?"

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_rate_limit_retry_exhausted(
        self, github_provider, sample_request
    ):
        """Test rate limit with retries exhausted."""
        # Always return 429
        mock_response = AsyncMock()
        mock_response.status = 429
        mock_response.text = AsyncMock(return_value="Rate limited")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        github_provider._session = mock_session
        github_provider.INITIAL_RETRY_DELAY = 0.01

        # Should raise after max retries
        with pytest.raises(ProviderRateLimitError, match="Rate limit exceeded"):
            await github_provider.generate(sample_request)

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_server_error_retry(
        self, github_provider, sample_request, mock_success_response
    ):
        """Test server error with successful retry."""
        # First call: 503, second call: 200
        mock_response_503 = AsyncMock()
        mock_response_503.status = 503
        mock_response_503.text = AsyncMock(return_value="Service unavailable")
        mock_response_503.__aenter__ = AsyncMock(return_value=mock_response_503)
        mock_response_503.__aexit__ = AsyncMock(return_value=None)

        mock_response_200 = AsyncMock()
        mock_response_200.status = 200
        mock_response_200.json = AsyncMock(return_value=mock_success_response)
        mock_response_200.__aenter__ = AsyncMock(return_value=mock_response_200)
        mock_response_200.__aexit__ = AsyncMock(return_value=None)

        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return mock_response_503
            return mock_response_200

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=mock_post)
        mock_session.closed = False

        github_provider._session = mock_session
        github_provider.INITIAL_RETRY_DELAY = 0.01

        # Execute
        response = await github_provider.generate(sample_request)

        # Verify retry happened
        assert call_count == 2
        assert response.content == "Hello! How can I help you today?"

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_timeout_retry(
        self, github_provider, sample_request, mock_success_response
    ):
        """Test timeout with successful retry."""
        call_count = 0

        def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise asyncio.TimeoutError("Request timeout")

            mock_response = AsyncMock()
            mock_response.status = 200
            mock_response.json = AsyncMock(return_value=mock_success_response)
            mock_response.__aenter__ = AsyncMock(return_value=mock_response)
            mock_response.__aexit__ = AsyncMock(return_value=None)
            return mock_response

        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=mock_post)
        mock_session.closed = False

        github_provider._session = mock_session
        github_provider.INITIAL_RETRY_DELAY = 0.01

        # Execute
        response = await github_provider.generate(sample_request)

        # Verify retry happened
        assert call_count == 2
        assert response.content == "Hello! How can I help you today?"

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_generate_client_error_no_retry(
        self, github_provider, sample_request
    ):
        """Test client error (400) does not retry."""
        mock_response = AsyncMock()
        mock_response.status = 400
        mock_response.text = AsyncMock(return_value="Invalid schema")
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        github_provider._session = mock_session

        # Should fail immediately without retry
        with pytest.raises(ProviderConnectionError, match="Invalid request"):
            await github_provider.generate(sample_request)

        # Verify only called once (no retry)
        assert mock_session.post.call_count == 1

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_get_models(self, github_provider):
        """Test getting available models."""
        models = await github_provider.get_models()

        assert len(models) > 0
        assert any(m.name == "gpt-4o" for m in models)
        assert any(m.name == "gpt-4o-mini" for m in models)

    @pytest.mark.asyncio
    async def test_health_check_success(self, github_provider):
        """Test health check with API available."""
        mock_response = AsyncMock()
        mock_response.status = 200
        mock_response.__aenter__ = AsyncMock(return_value=mock_response)
        mock_response.__aexit__ = AsyncMock(return_value=None)

        mock_session = AsyncMock()
        mock_session.post = MagicMock(return_value=mock_response)
        mock_session.closed = False

        github_provider._session = mock_session

        result = await github_provider.health_check()
        assert result is True

        await github_provider.close()

    @pytest.mark.asyncio
    async def test_health_check_failure(self, github_provider):
        """Test health check with API unavailable."""
        mock_session = AsyncMock()
        mock_session.post = MagicMock(side_effect=Exception("Connection failed"))

        github_provider._session = mock_session

        result = await github_provider.health_check()
        assert result is False
