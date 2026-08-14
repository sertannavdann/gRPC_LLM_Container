"""
Unit tests for D-08: LLM-generated plain-language module walkthroughs.

Covers:
    - LLMGateway.generate_text() — plain-prose lane (Task 1)
    - generate_walkthrough() tool + manifest field + validator hook (Task 2)
"""
import sys
import json
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

# Mock llm_pb2 to avoid import errors (llm_service protobuf stubs are generated
# at build time and are not present in the test environment; mirrors the
# pattern used by tests/unit/providers/test_llm_gateway.py)
sys.modules['llm_service.llm_pb2'] = MagicMock()
sys.modules['llm_service.llm_pb2_grpc'] = MagicMock()

from shared.providers.base_provider import (
    BaseProvider,
    ProviderConfig,
    ProviderType,
    ChatRequest,
    ChatResponse,
    ChatMessage,
    ProviderConnectionError,
)
from shared.providers.llm_gateway import (
    LLMGateway,
    Purpose,
    RoutingPolicy,
    ModelPreference,
    AllModelsFailedError,
)


class StubProvider(BaseProvider):
    """Minimal stub provider for gateway tests — captures the issued request."""

    def __init__(self, response_text: str = "stub response", should_fail: bool = False):
        super().__init__(ProviderConfig(provider_type=ProviderType.LOCAL))
        self.response_text = response_text
        self.should_fail = should_fail
        self.last_request: ChatRequest = None
        self.call_count = 0

    async def generate(self, request: ChatRequest) -> ChatResponse:
        self.call_count += 1
        self.last_request = request
        if self.should_fail:
            raise ProviderConnectionError("stub connection failure")
        return ChatResponse(
            model=request.model,
            content=self.response_text,
            stop_reason="stop",
            usage={"prompt_tokens": 10, "completion_tokens": 20},
        )

    async def generate_stream(self, request: ChatRequest):
        yield self.response_text

    async def get_models(self):
        return []

    async def health_check(self) -> bool:
        return True


def _make_gateway(provider: StubProvider, purpose: Purpose = Purpose.CRITIC) -> LLMGateway:
    policy = RoutingPolicy()
    prefs = [ModelPreference(provider_name="stub", model_name="stub-model", priority=0)]
    if purpose == Purpose.CRITIC:
        policy.critic = prefs
    elif purpose == Purpose.CODEGEN:
        policy.codegen = prefs
    elif purpose == Purpose.REPAIR:
        policy.repair = prefs
    return LLMGateway(providers={"stub": provider}, routing_policy=policy, max_retries=1)


# ============================================================================
# Task 1: LLMGateway.generate_text()
# ============================================================================


@pytest.mark.asyncio
async def test_generate_text_returns_raw_content():
    provider = StubProvider(response_text="This module talks to a weather API.")
    gateway = _make_gateway(provider)

    text, metadata = await gateway.generate_text(
        purpose=Purpose.CRITIC,
        messages=[ChatMessage(role="user", content="describe this code")],
    )

    assert text == "This module talks to a weather API."
    assert metadata["provider"] == "stub"
    assert metadata["model"] == "stub-model"
    assert metadata["usage"] == {"prompt_tokens": 10, "completion_tokens": 20}


@pytest.mark.asyncio
async def test_generate_text_no_response_format_in_request():
    provider = StubProvider()
    gateway = _make_gateway(provider)

    await gateway.generate_text(
        purpose=Purpose.CRITIC,
        messages=[ChatMessage(role="user", content="hello")],
    )

    assert provider.last_request is not None
    assert "response_format" not in (provider.last_request.extra or {})


@pytest.mark.asyncio
async def test_generate_text_fallthrough_on_first_provider_failure():
    failing_provider = StubProvider(should_fail=True)
    working_provider = StubProvider(response_text="fallback succeeded")

    policy = RoutingPolicy()
    policy.critic = [
        ModelPreference(provider_name="failing", model_name="model-a", priority=0),
        ModelPreference(provider_name="working", model_name="model-b", priority=1),
    ]
    gateway = LLMGateway(
        providers={"failing": failing_provider, "working": working_provider},
        routing_policy=policy,
        max_retries=1,
    )

    text, metadata = await gateway.generate_text(
        purpose=Purpose.CRITIC,
        messages=[ChatMessage(role="user", content="hello")],
    )

    assert text == "fallback succeeded"
    assert metadata["provider"] == "working"


@pytest.mark.asyncio
async def test_generate_text_all_models_failed_raises():
    provider = StubProvider(should_fail=True)
    gateway = _make_gateway(provider)

    with pytest.raises(AllModelsFailedError):
        await gateway.generate_text(
            purpose=Purpose.CRITIC,
            messages=[ChatMessage(role="user", content="hello")],
        )


@pytest.mark.asyncio
async def test_generate_text_no_preferences_raises_value_error():
    provider = StubProvider()
    policy = RoutingPolicy()  # no critic preferences configured
    gateway = LLMGateway(providers={"stub": provider}, routing_policy=policy, max_retries=1)

    with pytest.raises(ValueError):
        await gateway.generate_text(
            purpose=Purpose.CRITIC,
            messages=[ChatMessage(role="user", content="hello")],
        )


@pytest.mark.asyncio
async def test_generate_text_records_usage_identically_to_generate():
    provider = StubProvider(response_text="prose output")
    gateway = _make_gateway(provider)

    await gateway.generate_text(
        purpose=Purpose.CRITIC,
        messages=[ChatMessage(role="user", content="hello")],
        job_id="job-123",
    )

    usage = gateway.get_job_usage("job-123")
    assert usage is not None
    assert usage.total_tokens == 30
    assert usage.request_count == 1


# ============================================================================
# Task 2: generate_walkthrough() tool
# ============================================================================


class StubGatewayForWalkthrough:
    """Stub gateway exposing only generate_text(), matching LLMGateway's async signature."""

    def __init__(self, text: str = "This module fetches weather data.", raise_error: bool = False):
        self.text = text
        self.raise_error = raise_error
        self.calls = []

    async def generate_text(self, purpose, messages, job_id=None, temperature=0.3, max_tokens=None):
        self.calls.append({"purpose": purpose, "messages": messages, "job_id": job_id})
        if self.raise_error:
            raise RuntimeError("stub gateway failure")
        return self.text, {"provider": "stub", "model": "stub-model", "usage": {}}


@pytest.fixture
def module_dir_with_adapter(tmp_path):
    module_dir = tmp_path / "gaming" / "clashroyale"
    module_dir.mkdir(parents=True)
    (module_dir / "adapter.py").write_text(
        "from shared.adapters.base import BaseAdapter\n\n"
        "class ClashRoyaleAdapter(BaseAdapter):\n"
        "    def fetch_raw(self):\n"
        "        return {}\n"
    )
    return module_dir


def test_generate_walkthrough_returns_text_when_gateway_wired(monkeypatch, module_dir_with_adapter):
    import tools.builtin.module_builder as module_builder
    import tools.builtin.module_walkthrough as module_walkthrough

    stub_gateway = StubGatewayForWalkthrough(text="This module fetches Clash Royale player stats.")
    monkeypatch.setattr(module_builder, "_llm_gateway", stub_gateway)

    result = module_walkthrough.generate_walkthrough("gaming/clashroyale", module_dir_with_adapter)

    assert result == "This module fetches Clash Royale player stats."
    assert len(stub_gateway.calls) == 1
    assert stub_gateway.calls[0]["purpose"] == Purpose.CRITIC


def test_generate_walkthrough_returns_empty_when_no_gateway(monkeypatch, module_dir_with_adapter):
    import tools.builtin.module_builder as module_builder
    import tools.builtin.module_walkthrough as module_walkthrough

    monkeypatch.setattr(module_builder, "_llm_gateway", None)

    result = module_walkthrough.generate_walkthrough("gaming/clashroyale", module_dir_with_adapter)

    assert result == ""


def test_generate_walkthrough_returns_empty_when_adapter_missing(monkeypatch, tmp_path):
    import tools.builtin.module_builder as module_builder
    import tools.builtin.module_walkthrough as module_walkthrough

    empty_dir = tmp_path / "empty_module"
    empty_dir.mkdir()

    stub_gateway = StubGatewayForWalkthrough()
    monkeypatch.setattr(module_builder, "_llm_gateway", stub_gateway)

    result = module_walkthrough.generate_walkthrough("gaming/nothing", empty_dir)

    assert result == ""
    assert len(stub_gateway.calls) == 0


def test_generate_walkthrough_returns_empty_on_gateway_exception(monkeypatch, module_dir_with_adapter):
    import tools.builtin.module_builder as module_builder
    import tools.builtin.module_walkthrough as module_walkthrough

    stub_gateway = StubGatewayForWalkthrough(raise_error=True)
    monkeypatch.setattr(module_builder, "_llm_gateway", stub_gateway)

    result = module_walkthrough.generate_walkthrough("gaming/clashroyale", module_dir_with_adapter)

    assert result == ""


def test_generate_walkthrough_prompt_includes_source_and_reviewer_framing(monkeypatch, module_dir_with_adapter):
    import tools.builtin.module_builder as module_builder
    import tools.builtin.module_walkthrough as module_walkthrough

    stub_gateway = StubGatewayForWalkthrough()
    monkeypatch.setattr(module_builder, "_llm_gateway", stub_gateway)

    module_walkthrough.generate_walkthrough("gaming/clashroyale", module_dir_with_adapter)

    messages = stub_gateway.calls[0]["messages"]
    all_content = "\n".join(m.content for m in messages)
    assert "ClashRoyaleAdapter" in all_content
    assert "gaming/clashroyale" in all_content
    # System message frames the reviewer-approval context
    system_msgs = [m for m in messages if m.role == "system"]
    assert system_msgs
    assert "review" in system_msgs[0].content.lower() or "approve" in system_msgs[0].content.lower()


# ============================================================================
# Task 2: manifest field
# ============================================================================


def test_manifest_walkthrough_field_defaults_and_round_trips(tmp_path):
    from shared.modules.manifest import ModuleManifest

    manifest = ModuleManifest(name="x", category="gaming", platform="clashroyale")
    assert manifest.walkthrough == ""
    assert "walkthrough" in manifest.to_dict()

    manifest.walkthrough = "This module talks to the Clash Royale API."
    saved_path = manifest.save(tmp_path)
    loaded = ModuleManifest.load(saved_path)

    assert loaded.walkthrough == "This module talks to the Clash Royale API."


def test_manifest_approved_bundle_sha256_field_intact():
    """Guard: plan 08-02's field must not be disturbed by this plan's edit."""
    from shared.modules.manifest import ModuleManifest

    manifest = ModuleManifest(name="x")
    assert manifest.approved_bundle_sha256 == ""


# ============================================================================
# Task 2: validator finalize hook
# ============================================================================


@pytest.fixture
def validated_module(tmp_path, monkeypatch):
    """Set up a module dir + manifest and point module_validator.MODULES_DIR at tmp_path."""
    import tools.builtin.module_validator as module_validator

    modules_dir = tmp_path / "modules"
    module_dir = modules_dir / "gaming" / "clashroyale"
    module_dir.mkdir(parents=True)

    (module_dir / "adapter.py").write_text(
        "from shared.adapters.base import BaseAdapter\n\n"
        "class ClashRoyaleAdapter(BaseAdapter):\n"
        "    def fetch_raw(self):\n"
        "        return {}\n"
    )

    manifest = {
        "name": "clashroyale",
        "category": "gaming",
        "platform": "clashroyale",
        "version": "1.0.0",
    }
    (module_dir / "manifest.json").write_text(json.dumps(manifest, indent=2))

    monkeypatch.setattr(module_validator, "MODULES_DIR", modules_dir)

    return {"modules_dir": modules_dir, "module_dir": module_dir, "module_id": "gaming/clashroyale"}


def test_validate_module_validated_stores_walkthrough(monkeypatch, validated_module):
    import tools.builtin.module_validator as module_validator
    import tools.builtin.module_walkthrough as module_walkthrough
    from shared.modules.manifest import ModuleManifest

    monkeypatch.setattr(
        module_walkthrough, "generate_walkthrough", lambda module_id, module_dir: "Plain-language summary."
    )
    # Skip sandbox runtime checks by removing test_adapter.py — static-only path
    # (test_file.exists() is False -> report stays VALIDATED from static checks)

    result = module_validator.validate_module(validated_module["module_id"])

    assert result["status"] == "success"
    manifest = ModuleManifest.load(validated_module["module_dir"] / "manifest.json")
    assert manifest.walkthrough == "Plain-language summary."


def test_validate_module_failed_leaves_walkthrough_empty(monkeypatch, validated_module):
    import tools.builtin.module_validator as module_validator
    import tools.builtin.module_walkthrough as module_walkthrough
    from shared.modules.manifest import ModuleManifest

    # Force a static failure by writing invalid syntax
    (validated_module["module_dir"] / "adapter.py").write_text("def broken(:\n")

    called = {"count": 0}

    def _spy(module_id, module_dir):
        called["count"] += 1
        return "should not be called"

    monkeypatch.setattr(module_walkthrough, "generate_walkthrough", _spy)

    result = module_validator.validate_module(validated_module["module_id"])

    assert result["status"] == "failed"
    assert called["count"] == 0
    manifest = ModuleManifest.load(validated_module["module_dir"] / "manifest.json")
    assert manifest.walkthrough == ""


def test_validate_module_walkthrough_exception_does_not_affect_validation(monkeypatch, validated_module):
    import tools.builtin.module_validator as module_validator
    import tools.builtin.module_walkthrough as module_walkthrough
    from shared.modules.manifest import ModuleManifest

    def _raise(module_id, module_dir):
        raise RuntimeError("walkthrough generation blew up")

    monkeypatch.setattr(module_walkthrough, "generate_walkthrough", _raise)

    result = module_validator.validate_module(validated_module["module_id"])

    # Validation must still succeed; only the walkthrough generation failed
    assert result["status"] == "success"
    manifest = ModuleManifest.load(validated_module["module_dir"] / "manifest.json")
    assert manifest.walkthrough == ""
