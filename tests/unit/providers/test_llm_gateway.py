"""Unit tests for LLM Gateway routing layer."""

import sys
import pytest
import json
from unittest.mock import AsyncMock, MagicMock, patch

# Mock llm_pb2 to avoid import errors
sys.modules['llm_service.llm_pb2'] = MagicMock()
sys.modules['llm_service.llm_pb2_grpc'] = MagicMock()

from shared.providers.llm_gateway import (
    LLMGateway,
    RoutingPolicy,
    ModelPreference,
    BudgetConfig,
    Purpose,
    SchemaValidationError,
    BudgetExceededError,
    AllModelsFailedError,
)
from shared.providers.base_provider import (
    BaseProvider,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderConnectionError,
)


@pytest.fixture
def routing_policy():
    """Create test routing policy."""
    return RoutingPolicy(
        codegen=[
            ModelPreference(provider_name="github", model_name="gpt-4o", priority=0),
            ModelPreference(provider_name="openai", model_name="gpt-4o", priority=1),
        ],
        repair=[
            ModelPreference(provider_name="github", model_name="gpt-4o-mini", priority=0),
        ],
        critic=[
            ModelPreference(provider_name="openai", model_name="gpt-4o", priority=0),
        ],
    )


@pytest.fixture
def budget_config():
    """Create test budget config."""
    return BudgetConfig(
        max_tokens_per_request=4000,
        max_tokens_per_job=10000,
    )


@pytest.fixture
def mock_provider():
    """Create mock provider."""
    provider = AsyncMock(spec=BaseProvider)
    provider.name = "test_provider"
    return provider


@pytest.fixture
def sample_messages():
    """Create sample chat messages."""
    return [
        ChatMessage(role="system", content="You are a code generator."),
        ChatMessage(role="user", content="Generate a Python adapter."),
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
                "content": "# adapter code here",
            }
        ],
        "deleted_files": [],
        "assumptions": ["API key available", "Rate limit: 60 calls/min"],
        "rationale": "Implemented OpenWeather API adapter with rate limiting",
        "policy": "AdapterContractSpec",
        "validation_report": {"valid": True, "errors": []},
    }


class TestRoutingPolicy:
    """Test suite for RoutingPolicy."""

    def test_get_preferences_codegen(self, routing_policy):
        """Test getting codegen preferences."""
        prefs = routing_policy.get_preferences(Purpose.CODEGEN)

        assert len(prefs) == 2
        assert prefs[0].provider_name == "github"
        assert prefs[0].priority == 0
        assert prefs[1].provider_name == "openai"
        assert prefs[1].priority == 1

    def test_get_preferences_repair(self, routing_policy):
        """Test getting repair preferences."""
        prefs = routing_policy.get_preferences(Purpose.REPAIR)

        assert len(prefs) == 1
        assert prefs[0].provider_name == "github"
        assert prefs[0].model_name == "gpt-4o-mini"

    def test_get_preferences_critic(self, routing_policy):
        """Test getting critic preferences."""
        prefs = routing_policy.get_preferences(Purpose.CRITIC)

        assert len(prefs) == 1
        assert prefs[0].provider_name == "openai"

    def test_from_dict(self):
        """Test creating policy from dictionary."""
        data = {
            "codegen": [
                {"provider": "github", "model": "gpt-4o", "priority": 0},
                {"provider": "openai", "model": "gpt-4o", "priority": 1},
            ],
            "repair": [
                {"provider": "github", "model": "gpt-4o-mini", "priority": 0},
            ],
            "critic": [],
        }

        policy = RoutingPolicy.from_dict(data)

        assert len(policy.codegen) == 2
        assert len(policy.repair) == 1
        assert len(policy.critic) == 0


class TestLLMGateway:
    """Test suite for LLMGateway."""

    def test_initialization(self, routing_policy, budget_config):
        """Test gateway initialization."""
        gateway = LLMGateway(
            providers={},
            routing_policy=routing_policy,
            budget_config=budget_config,
        )

        assert gateway.routing_policy == routing_policy
        assert gateway.budget_config.max_tokens_per_request == 4000
        assert len(gateway.job_budgets) == 0

    def test_register_provider(self, routing_policy, mock_provider):
        """Test provider registration."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        gateway.register_provider("test", mock_provider)

        assert "test" in gateway.providers
        assert gateway.providers["test"] == mock_provider

    def test_set_job_budget(self, routing_policy):
        """Test setting job budget."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        gateway.set_job_budget("job-123", 5000)

        budget = gateway.get_job_usage("job-123")
        assert budget is not None
        assert budget.job_id == "job-123"
        assert budget.max_tokens == 5000
        assert budget.total_tokens == 0

    def test_check_budget_per_request_limit(self, routing_policy, budget_config):
        """Test per-request budget check."""
        gateway = LLMGateway(
            providers={},
            routing_policy=routing_policy,
            budget_config=budget_config,
        )

        # Should raise if exceeds per-request limit
        with pytest.raises(BudgetExceededError, match="per-request limit"):
            gateway._check_budget(None, 5000)  # budget_config.max = 4000

    def test_check_budget_per_job_limit(self, routing_policy, budget_config):
        """Test per-job budget check."""
        gateway = LLMGateway(
            providers={},
            routing_policy=routing_policy,
            budget_config=budget_config,
        )

        # Set job budget
        gateway.set_job_budget("job-123", 1000)

        # Use 800 tokens
        gateway.job_budgets["job-123"].total_tokens = 800

        # Request 300 should fail (800 + 300 > 1000)
        with pytest.raises(BudgetExceededError, match="remaining job budget"):
            gateway._check_budget("job-123", 300)

    def test_record_usage(self, routing_policy):
        """Test token usage recording."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        response = ChatResponse(
            model="gpt-4o",
            content="test",
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )

        gateway._record_usage("job-123", response)

        budget = gateway.get_job_usage("job-123")
        assert budget.total_tokens == 150
        assert budget.request_count == 1

    def test_validate_schema_success(self, routing_policy, valid_response_json):
        """Test successful schema validation."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        response_text = json.dumps(valid_response_json)
        allowed_dirs = ["modules/weather/openweather"]

        contract = gateway._validate_schema(response_text, allowed_dirs)

        assert contract.stage == "adapter"
        assert contract.module == "weather/openweather"
        assert len(contract.changed_files) == 1

    def test_validate_schema_invalid_json(self, routing_policy):
        """Test schema validation with invalid JSON."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        with pytest.raises(SchemaValidationError, match="Invalid JSON"):
            gateway._validate_schema("not json", [])

    def test_validate_schema_missing_field(self, routing_policy, valid_response_json):
        """Test schema validation with missing required field."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        # Remove required field
        del valid_response_json["stage"]
        response_text = json.dumps(valid_response_json)

        with pytest.raises(SchemaValidationError, match="Schema validation failed"):
            gateway._validate_schema(response_text, [])

    def test_validate_schema_disallowed_path(self, routing_policy, valid_response_json):
        """Test schema validation with disallowed file path."""
        gateway = LLMGateway(providers={}, routing_policy=routing_policy)

        response_text = json.dumps(valid_response_json)
        # Don't allow the path in the response
        allowed_dirs = ["modules/gaming/steam"]

        with pytest.raises(SchemaValidationError, match="Contract validation failed"):
            gateway._validate_schema(response_text, allowed_dirs)

    @pytest.mark.asyncio
    async def test_generate_success(
        self,
        routing_policy,
        mock_provider,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test successful generation."""
        # Setup mock provider
        response = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider.generate = AsyncMock(return_value=response)

        gateway = LLMGateway(
            providers={"github": mock_provider},
            routing_policy=routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify
        assert contract.stage == "adapter"
        assert contract.module == "weather/openweather"
        assert metadata["provider"] == "github"
        assert metadata["model"] == "gpt-4o"
        assert metadata["usage"]["prompt_tokens"] == 100

    @pytest.mark.asyncio
    async def test_generate_with_job_budget(
        self,
        routing_policy,
        mock_provider,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test generation with job budget tracking."""
        response = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider.generate = AsyncMock(return_value=response)

        # Use smaller budget config to avoid conflict
        budget_config = BudgetConfig(max_tokens_per_request=4000)

        gateway = LLMGateway(
            providers={"github": mock_provider},
            routing_policy=routing_policy,
            budget_config=budget_config,
        )

        # Set job budget larger than per-request limit
        gateway.set_job_budget("job-123", 10000)

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
            job_id="job-123",
        )

        # Verify usage tracked
        budget = gateway.get_job_usage("job-123")
        assert budget.total_tokens == 300  # 100 prompt + 200 completion
        assert budget.request_count == 1

    @pytest.mark.asyncio
    async def test_generate_fallback_on_error(
        self,
        routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test fallback to next model on error."""
        # First provider fails
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
            routing_policy=routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback happened
        assert metadata["provider"] == "openai"
        assert metadata["attempt"] == 2  # Second attempt succeeded

    @pytest.mark.asyncio
    async def test_generate_all_models_fail(
        self,
        routing_policy,
        sample_messages,
        sample_schema,
    ):
        """Test all models failing."""
        # Both providers fail
        mock_provider1 = AsyncMock(spec=BaseProvider)
        mock_provider1.generate = AsyncMock(
            side_effect=ProviderRateLimitError("Rate limited")
        )

        mock_provider2 = AsyncMock(spec=BaseProvider)
        mock_provider2.generate = AsyncMock(
            side_effect=ProviderConnectionError("Connection failed")
        )

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=routing_policy,
        )

        # Should raise AllModelsFailedError
        with pytest.raises(AllModelsFailedError) as exc_info:
            await gateway.generate(
                purpose=Purpose.CODEGEN,
                messages=sample_messages,
                schema=sample_schema,
                allowed_dirs=["modules/weather/openweather"],
            )

        assert exc_info.value.purpose == Purpose.CODEGEN
        assert len(exc_info.value.errors) == 2

    @pytest.mark.asyncio
    async def test_generate_schema_validation_error_triggers_fallback(
        self,
        routing_policy,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test schema validation error triggers fallback."""
        # First provider returns invalid response
        mock_provider1 = AsyncMock(spec=BaseProvider)
        invalid_response = ChatResponse(
            model="gpt-4o",
            content='{"invalid": "response"}',  # Missing required fields
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 50},
        )
        mock_provider1.generate = AsyncMock(return_value=invalid_response)

        # Second provider returns valid response
        mock_provider2 = AsyncMock(spec=BaseProvider)
        valid_response = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider2.generate = AsyncMock(return_value=valid_response)

        gateway = LLMGateway(
            providers={"github": mock_provider1, "openai": mock_provider2},
            routing_policy=routing_policy,
        )

        # Execute
        contract, metadata = await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
        )

        # Verify fallback to second provider
        assert metadata["provider"] == "openai"
        assert metadata["attempt"] == 2

    @pytest.mark.asyncio
    async def test_generate_with_seed(
        self,
        routing_policy,
        mock_provider,
        sample_messages,
        sample_schema,
        valid_response_json,
    ):
        """Test generation with seed for reproducibility."""
        response = ChatResponse(
            model="gpt-4o",
            content=json.dumps(valid_response_json),
            stop_reason="stop",
            usage={"prompt_tokens": 100, "completion_tokens": 200},
        )
        mock_provider.generate = AsyncMock(return_value=response)

        gateway = LLMGateway(
            providers={"github": mock_provider},
            routing_policy=routing_policy,
        )

        # Execute with seed
        await gateway.generate(
            purpose=Purpose.CODEGEN,
            messages=sample_messages,
            schema=sample_schema,
            allowed_dirs=["modules/weather/openweather"],
            seed=42,
        )

        # Verify seed was passed to provider
        call_args = mock_provider.generate.call_args
        request = call_args[0][0]
        assert request.extra.get("seed") == 42

    def test_get_routing_info(self, routing_policy, budget_config):
        """Test getting routing information."""
        gateway = LLMGateway(
            providers={"github": MagicMock(), "openai": MagicMock()},
            routing_policy=routing_policy,
            budget_config=budget_config,
        )

        info = gateway.get_routing_info()

        assert "github" in info["providers"]
        assert "openai" in info["providers"]
        assert len(info["routing"]["codegen"]) == 2
        assert info["routing"]["codegen"][0]["provider"] == "github"
        assert info["budget"]["max_tokens_per_request"] == 4000
