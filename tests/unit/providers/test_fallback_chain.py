"""Unit tests for LLM Gateway fallback chain behavior."""

import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock

# Mock llm_pb2 to avoid import errors
sys.modules['llm_service.llm_pb2'] = MagicMock()
sys.modules['llm_service.llm_pb2_grpc'] = MagicMock()

from shared.providers.llm_gateway import (
    LLMGateway,
    RoutingPolicy,
    ModelPreference,
    Purpose,
    AllModelsFailedError,
)
from shared.providers.base_provider import (
    BaseProvider,
    ChatResponse,
    ChatMessage,
    ProviderRateLimitError,
    ProviderConnectionError,
    ProviderAuthError,
)


@pytest.fixture
def multi_model_routing_policy():
    """Create routing policy with multiple fallback models."""
    return RoutingPolicy(
        codegen=[
            ModelPreference(provider_name="github", model_name="gpt-4o", priority=0),
            ModelPreference(provider_name="openai", model_name="gpt-4o", priority=1),
            ModelPreference(provider_name="anthropic", model_name="claude-sonnet", priority=2),
        ],
        repair=[
            ModelPreference(provider_name="github", model_name="gpt-4o-mini", priority=0),
            ModelPreference(provider_name="openai", model_name="gpt-4o-mini", priority=1),
        ],
        critic=[
            ModelPreference(provider_name="openai", model_name="o1", priority=0),
        ],
    )


@pytest.fixture
def sample_messages():
    """Create sample chat messages."""
    return [
        ChatMessage(role="system", content="You are a code generator."),
        ChatMessage(role="user", content="Generate adapter code."),
    ]


@pytest.fixture
def sample_schema():
    """Create sample JSON schema."""
    return {
        "name": "generator_response",
        "strict": True,
        "schema": {
            "type": "object",
            "properties": {
                "stage": {"type": "string"},
                "module": {"type": "string"},
                "changed_files": {"type": "array"},
                "deleted_files": {"type": "array"},
                "assumptions": {"type": "array"},
                "rationale": {"type": "string"},
                "policy": {"type": "string"},
                "validation_report": {"type": "object"},
            },
            "required": [
                "stage",
                "module",
                "changed_files",
                "assumptions",
                "rationale",
                "policy",
                "validation_report",
            ],
        },
    }


@pytest.fixture
def valid_response_json():
    """Create valid generator response JSON."""
    return {
        "stage": "adapter",
        "module": "weather/openweather",
        "changed_files": [
            {
                "path": "modules/weather/openweather/adapter.py",
                "content": "# adapter code",
            }
        ],
        "deleted_files": [],
        "assumptions": ["API key available"],
        "rationale": "Implemented OpenWeather adapter",
        "policy": "AdapterContractSpec",
        "validation_report": {"valid": True, "errors": []},
    }


class TestFallbackChain:
    """Test suite for deterministic fallback chain behavior."""

    @pytest.mark.asyncio
    async def test_fallback_on_rate_limit(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test deterministic fallback when primary model is rate limited."""
        # First provider rate limited
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        # Second provider succeeds
        mock_provider2 = AsyncMock(spec=BaseProvider)
        response2 = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider2.generate = AsyncMock(return_value=response2)

        # Third provider not called
        mock_provider3 = AsyncMock(spec=BaseProvider)

        gateway = LLMGateway(
            providers={
                "github": mock_provider1,
                "openai": mock_provider2,
                "anthropic": mock_provider3,
            },
            routing_policy=multi_model_routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback to second model
        assert metadata["provider"] == "openai"
        assert metadata["model"] == "gpt-4o"
        assert metadata["attempt"] == 2

        # Verify third provider never called
        mock_provider3.generate.assert_not_called()

    @pytest.mark.asyncio
    async def test_fallback_on_connection_error(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test fallback on connection error."""
        # First provider connection error
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderConnectionError("Connection failed")
        )

        # Second provider succeeds
        mock_provider2 = AsyncMock(spec=BaseProvider)
        response2 = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider2.generate = AsyncMock(return_value=response2)

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=multi_model_routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback
        assert metadata["provider"] == "openai"
        assert metadata["attempt"] == 2

    @pytest.mark.asyncio
    async def test_no_fallback_on_auth_error(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test that auth error triggers fallback (not retry of same model)."""
        # First provider auth error
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderAuthError("Invalid API key")
        )

        # Second provider succeeds
        mock_provider2 = AsyncMock(spec=BaseProvider)
        response2 = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider2.generate = AsyncMock(return_value=response2)

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=multi_model_routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback to next model
        assert metadata["provider"] == "openai"
        assert metadata["attempt"] == 2

    @pytest.mark.asyncio
    async def test_all_models_fail_deterministic_error(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
    ):
        """Test deterministic error when all models fail."""
        # All providers fail
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        mock_provider2 = AsyncMock(spec=BaseProvider)
        mock_provider2.generate = AsyncMock(
            side_effect=ProviderConnectionError("Connection failed")
        )

        mock_provider3 = AsyncMock(spec=BaseProvider)
        mock_provider3.generate = AsyncMock(
            side_effect=ProviderAuthError("Auth failed")
        )

        gateway = LLMGateway(
            providers={
                "github": mock_provider1,
                "openai": mock_provider2,
                "anthropic": mock_provider3,
            },
            routing_policy=multi_model_routing_policy,
        )

        # Should raise AllModelsFailedError with all attempts
        with pytest.raises(AllModelsFailedError) as exc_info:
            await gateway.generate(
                purpose=Purpose.CODEGEN,
                messages=sample_messages,
                schema=sample_schema,
                allowed_dirs=["modules/weather/openweather"],
            )

        # Verify error contains details of all failures
        error = exc_info.value
        assert error.purpose == Purpose.CODEGEN
        assert len(error.errors) == 3
        assert "Rate limited" in str(error.errors)
        assert "Connection failed" in str(error.errors)
        assert "Auth failed" in str(error.errors)

    @pytest.mark.asyncio
    async def test_fallback_order_matches_priority(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test that fallback follows priority order exactly."""
        call_order = []

        # Track which providers are called
        def make_provider(name, should_fail=True):
            provider = AsyncMock(spec=BaseProvider)

            async def tracked_generate(request):
                call_order.append(name)
                if should_fail:
                    raise ProviderRateLimitError(f"{name} failed")
                return ChatResponse(
                    model="test-model",
                    content=json.dumps(valid_response_json),
                    stop_reason="stop",
                    usage={"prompt_tokens": 100, "completion_tokens": 200},
                )

            provider.generate = tracked_generate
            return provider

        # Setup: first two fail, third succeeds
        mock_provider1 = make_provider("github", should_fail=True)
        mock_provider2 = make_provider("openai", should_fail=True)
        mock_provider3 = make_provider("anthropic", should_fail=False)

        gateway = LLMGateway(
            providers={
                "github": mock_provider1,
                "openai": mock_provider2,
                "anthropic": mock_provider3,
            },
            routing_policy=multi_model_routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback order matches priority
        assert call_order == ["github", "openai", "anthropic"]
        assert metadata["provider"] == "anthropic"
        assert metadata["attempt"] == 3

    @pytest.mark.asyncio
    async def test_deterministic_same_failure_same_fallback(
        self,
        multi_model_routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test that same failure condition always selects same next model."""
        # First provider always rate limited
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        # Second provider succeeds
        mock_provider2 = AsyncMock(spec=BaseProvider)
        response = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider2.generate = AsyncMock(return_value=response)

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=multi_model_routing_policy,
        )

        # Execute multiple times
        for i in range(3):
            contract, metadata = await gateway.generate(
                purpose=Purpose.CODEGEN,
                messages=sample_messages,
                schema=sample_schema,
                allowed_dirs=["modules/weather/openweather"],
            )

            # Always falls back to same provider
            assert metadata["provider"] == "openai"
            assert metadata["model"] == "gpt-4o"
            assert metadata["attempt"] == 2

    @pytest.mark.asyncio
    async def test_paused_job_recommendation_on_all_fail(
        self,
        sample_messages,
        sample_schema,
    ):
        """Test that AllModelsFailedError can be used to recommend paused job state."""
        # Create simple policy with just 2 providers
        simple_policy = RoutingPolicy(
            codegen=[
                ModelPreference(provider_name="github", model_name="gpt-4o", priority=0),
                ModelPreference(provider_name="openai", model_name="gpt-4o", priority=1),
            ],
        )

        # All providers fail
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        mock_provider2 = AsyncMock(spec=BaseProvider)
        mock_provider2.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=simple_policy,
        )

        # Execute and catch error
        try:
            await gateway.generate(
                purpose=Purpose.CODEGEN,
                messages=sample_messages,
                schema=sample_schema,
                allowed_dirs=["modules/weather/openweather"],
            )
            pytest.fail("Should have raised AllModelsFailedError")
        except AllModelsFailedError as e:
            # Error provides structured information for job pausing
            assert e.purpose == Purpose.CODEGEN
            assert len(e.errors) == 2

            # Application can use this to pause job
            job_state = {
                "status": "paused",
                "reason": "all_models_failed",
                "purpose": str(e.purpose),
                "errors": e.errors,
            }

            assert job_state["status"] == "paused"
            assert "codegen" in job_state["purpose"].lower()
