"""
LLM Gateway with purpose-based routing and schema enforcement.

Provides:
- Purpose lanes (codegen, repair, critic) with model preferences
- Response validation against GeneratorResponseContract
- Budget tracking and enforcement
- Deterministic fallback on model failures
"""

import logging
import json
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from .base_provider import (
    BaseProvider,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ProviderError,
    ProviderAuthError,
    ProviderRateLimitError,
    ProviderConnectionError,
)
from shared.modules.contracts import GeneratorResponseContract


logger = logging.getLogger(__name__)


class Purpose(str, Enum):
    """Purpose lanes for routing."""
    CODEGEN = "codegen"
    REPAIR = "repair"
    CRITIC = "critic"


@dataclass
class ModelPreference:
    """Model preference for a purpose lane."""
    provider_name: str
    model_name: str
    priority: int = 0  # Lower = higher priority


@dataclass
class RoutingPolicy:
    """
    Routing policy defining model preferences per purpose.

    Each purpose lane has an ordered list of model preferences.
    Fallback is deterministic: same failure always selects same next model.
    """
    codegen: List[ModelPreference] = field(default_factory=list)
    repair: List[ModelPreference] = field(default_factory=list)
    critic: List[ModelPreference] = field(default_factory=list)

    def get_preferences(self, purpose: Purpose) -> List[ModelPreference]:
        """Get model preferences for a purpose, sorted by priority."""
        if purpose == Purpose.CODEGEN:
            prefs = self.codegen
        elif purpose == Purpose.REPAIR:
            prefs = self.repair
        elif purpose == Purpose.CRITIC:
            prefs = self.critic
        else:
            raise ValueError(f"Unknown purpose: {purpose}")

        return sorted(prefs, key=lambda p: p.priority)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RoutingPolicy":
        """Create RoutingPolicy from dictionary."""
        def parse_prefs(pref_list: List[Dict]) -> List[ModelPreference]:
            return [
                ModelPreference(
                    provider_name=p["provider"],
                    model_name=p["model"],
                    priority=p.get("priority", 0),
                )
                for p in pref_list
            ]

        return cls(
            codegen=parse_prefs(data.get("codegen", [])),
            repair=parse_prefs(data.get("repair", [])),
            critic=parse_prefs(data.get("critic", [])),
        )


@dataclass
class BudgetConfig:
    """Budget constraints for LLM requests."""
    max_tokens_per_request: int = 8000
    max_tokens_per_job: Optional[int] = None  # None = unlimited


@dataclass
class JobBudget:
    """Budget tracking for a single job."""
    job_id: str
    total_tokens: int = 0
    request_count: int = 0
    max_tokens: Optional[int] = None


class SchemaValidationError(Exception):
    """Raised when LLM output fails schema validation."""
    pass


class BudgetExceededError(Exception):
    """Raised when budget is exceeded."""
    pass


class AllModelsFailedError(Exception):
    """Raised when all models in a lane fail."""

    def __init__(self, purpose: Purpose, errors: List[str]):
        self.purpose = purpose
        self.errors = errors
        super().__init__(
            f"All models failed for purpose '{purpose}'. Errors: {errors}"
        )


class LLMGateway:
    """
    Gateway for LLM requests with routing, validation, and budget control.

    Features:
    - Purpose-based routing to configured model preferences
    - Schema validation against GeneratorResponseContract
    - Per-request and per-job token budget enforcement
    - Deterministic fallback on model failures
    - Seed support for reproducibility
    """

    def __init__(
        self,
        providers: Dict[str, BaseProvider],
        routing_policy: RoutingPolicy,
        budget_config: Optional[BudgetConfig] = None,
    ):
        """
        Initialize LLM Gateway.

        Args:
            providers: Dictionary of provider_name -> provider instance
            routing_policy: RoutingPolicy defining model preferences
            budget_config: Optional budget constraints
        """
        self.providers = providers
        self.routing_policy = routing_policy
        self.budget_config = budget_config or BudgetConfig()
        self.job_budgets: Dict[str, JobBudget] = {}

        logger.info(
            f"LLMGateway initialized with {len(providers)} providers, "
            f"max_tokens_per_request={self.budget_config.max_tokens_per_request}"
        )

    def register_provider(self, name: str, provider: BaseProvider) -> None:
        """
        Register a new provider.

        Args:
            name: Provider name
            provider: Provider instance
        """
        self.providers[name] = provider
        logger.info(f"Registered provider: {name}")

    def set_job_budget(self, job_id: str, max_tokens: int) -> None:
        """
        Set token budget for a job.

        Args:
            job_id: Job identifier
            max_tokens: Maximum tokens for this job
        """
        self.job_budgets[job_id] = JobBudget(
            job_id=job_id,
            max_tokens=max_tokens,
        )
        logger.info(f"Set job budget for {job_id}: {max_tokens} tokens")

    def get_job_usage(self, job_id: str) -> Optional[JobBudget]:
        """
        Get current usage for a job.

        Args:
            job_id: Job identifier

        Returns:
            JobBudget if exists, None otherwise
        """
        return self.job_budgets.get(job_id)

    def _check_budget(
        self,
        job_id: Optional[str],
        requested_tokens: int,
    ) -> None:
        """
        Check if request is within budget.

        Args:
            job_id: Optional job identifier
            requested_tokens: Tokens requested

        Raises:
            BudgetExceededError: If budget would be exceeded
        """
        # Check per-request limit
        if requested_tokens > self.budget_config.max_tokens_per_request:
            raise BudgetExceededError(
                f"Requested {requested_tokens} tokens exceeds "
                f"per-request limit of {self.budget_config.max_tokens_per_request}"
            )

        # Check per-job limit if job_id provided
        if job_id and job_id in self.job_budgets:
            budget = self.job_budgets[job_id]
            if budget.max_tokens:
                remaining = budget.max_tokens - budget.total_tokens
                if requested_tokens > remaining:
                    raise BudgetExceededError(
                        f"Requested {requested_tokens} tokens exceeds "
                        f"remaining job budget of {remaining} "
                        f"(used {budget.total_tokens}/{budget.max_tokens})"
                    )

    def _record_usage(
        self,
        job_id: Optional[str],
        response: ChatResponse,
    ) -> None:
        """
        Record token usage for a request.

        Args:
            job_id: Optional job identifier
            response: Response with usage information
        """
        if not job_id or not response.usage:
            return

        if job_id not in self.job_budgets:
            self.job_budgets[job_id] = JobBudget(job_id=job_id)

        budget = self.job_budgets[job_id]
        total_tokens = response.usage.get("prompt_tokens", 0) + response.usage.get("completion_tokens", 0)
        budget.total_tokens += total_tokens
        budget.request_count += 1

        logger.debug(
            f"Job {job_id}: used {total_tokens} tokens "
            f"(total: {budget.total_tokens}, requests: {budget.request_count})"
        )

    def _validate_schema(
        self,
        response_text: str,
        allowed_dirs: List[str],
    ) -> GeneratorResponseContract:
        """
        Validate response against GeneratorResponseContract.

        Args:
            response_text: JSON response text from LLM
            allowed_dirs: Allowed directories for file changes

        Returns:
            Validated GeneratorResponseContract

        Raises:
            SchemaValidationError: If validation fails
        """
        try:
            # Parse JSON
            data = json.loads(response_text)
        except json.JSONDecodeError as e:
            raise SchemaValidationError(f"Invalid JSON response: {e}")

        try:
            # Validate with Pydantic
            contract = GeneratorResponseContract(**data)
        except Exception as e:
            raise SchemaValidationError(f"Schema validation failed: {e}")

        # Validate path allowlist
        validation_result = contract.validate_contract(allowed_dirs)
        if not validation_result["valid"]:
            errors = [err["message"] for err in validation_result["errors"]]
            raise SchemaValidationError(
                f"Contract validation failed: {'; '.join(errors)}"
            )

        return contract

    async def generate(
        self,
        purpose: Purpose,
        messages: List[ChatMessage],
        schema: Dict[str, Any],
        allowed_dirs: List[str],
        job_id: Optional[str] = None,
        temperature: float = 0.7,
        seed: Optional[int] = None,
    ) -> Tuple[GeneratorResponseContract, Dict[str, Any]]:
        """
        Generate LLM response with routing, validation, and fallback.

        Args:
            purpose: Purpose lane for routing
            messages: Chat messages
            schema: JSON schema for structured output
            allowed_dirs: Allowed directories for file changes
            job_id: Optional job ID for budget tracking
            temperature: Sampling temperature
            seed: Optional seed for reproducibility

        Returns:
            Tuple of (validated contract, metadata dict with provider/model/usage)

        Raises:
            BudgetExceededError: If budget exceeded
            SchemaValidationError: If response fails validation
            AllModelsFailedError: If all models fail
        """
        # Get model preferences for this purpose
        preferences = self.routing_policy.get_preferences(purpose)
        if not preferences:
            raise ValueError(f"No model preferences configured for purpose: {purpose}")

        # Check budget before attempting
        max_tokens = self.budget_config.max_tokens_per_request
        self._check_budget(job_id, max_tokens)

        # Try each model in order until success
        errors = []
        for pref in preferences:
            provider = self.providers.get(pref.provider_name)
            if not provider:
                error_msg = f"Provider '{pref.provider_name}' not registered"
                errors.append(error_msg)
                logger.warning(error_msg)
                continue

            try:
                logger.info(
                    f"Attempting generation with {pref.provider_name}/{pref.model_name} "
                    f"for purpose={purpose}"
                )

                # Build request
                request = ChatRequest(
                    messages=messages,
                    model=pref.model_name,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    extra={
                        "response_format": {
                            "type": "json_schema",
                            "json_schema": schema,
                        }
                    },
                )

                # Add seed if provided
                if seed is not None:
                    request.extra["seed"] = seed

                # Call provider
                response = await provider.generate(request)

                # Validate schema
                try:
                    contract = self._validate_schema(response.content, allowed_dirs)
                except SchemaValidationError as e:
                    # Schema validation error - this is NOT retryable with same model
                    error_msg = (
                        f"Schema validation failed for "
                        f"{pref.provider_name}/{pref.model_name}: {str(e)}"
                    )
                    errors.append(error_msg)
                    logger.error(error_msg)
                    continue

                # Record usage
                self._record_usage(job_id, response)

                # Success - return contract and metadata
                metadata = {
                    "provider": pref.provider_name,
                    "model": pref.model_name,
                    "usage": response.usage,
                    "attempt": len(errors) + 1,
                }

                logger.info(
                    f"Generation successful with {pref.provider_name}/{pref.model_name} "
                    f"(attempt {metadata['attempt']})"
                )

                return contract, metadata

            except ProviderAuthError as e:
                # Auth error - not retryable
                error_msg = f"Auth error with {pref.provider_name}: {str(e)}"
                errors.append(error_msg)
                logger.error(error_msg)
                continue

            except (ProviderRateLimitError, ProviderConnectionError) as e:
                # Transient error - try next model
                error_msg = (
                    f"Transient error with {pref.provider_name}/{pref.model_name}: "
                    f"{str(e)}"
                )
                errors.append(error_msg)
                logger.warning(error_msg)
                continue

            except Exception as e:
                # Unknown error - try next model
                error_msg = (
                    f"Unexpected error with {pref.provider_name}/{pref.model_name}: "
                    f"{str(e)}"
                )
                errors.append(error_msg)
                logger.error(error_msg)
                continue

        # All models failed
        raise AllModelsFailedError(purpose, errors)

    def get_routing_info(self) -> Dict[str, Any]:
        """
        Get current routing configuration information.

        Returns:
            Dictionary with routing policy and provider status
        """
        return {
            "providers": list(self.providers.keys()),
            "routing": {
                "codegen": [
                    {"provider": p.provider_name, "model": p.model_name, "priority": p.priority}
                    for p in sorted(self.routing_policy.codegen, key=lambda x: x.priority)
                ],
                "repair": [
                    {"provider": p.provider_name, "model": p.model_name, "priority": p.priority}
                    for p in sorted(self.routing_policy.repair, key=lambda x: x.priority)
                ],
                "critic": [
                    {"provider": p.provider_name, "model": p.model_name, "priority": p.priority}
                    for p in sorted(self.routing_policy.critic, key=lambda x: x.priority)
                ],
            },
            "budget": {
                "max_tokens_per_request": self.budget_config.max_tokens_per_request,
                "max_tokens_per_job": self.budget_config.max_tokens_per_job,
            },
        }
