"""Tier endpoints in routing_config.json may reference env vars, compose-style."""

from orchestrator.routing_config import RoutingConfig, TierConfig, expand_env


def test_expand_env_default_when_unset(monkeypatch):
    monkeypatch.delenv("LLM_HEAVY_HOST", raising=False)
    assert expand_env("${LLM_HEAVY_HOST:-llm_service:50051}") == "llm_service:50051"


def test_expand_env_uses_value(monkeypatch):
    monkeypatch.setenv("LLM_HEAVY_HOST", "host.docker.internal:50051")
    assert expand_env("${LLM_HEAVY_HOST:-llm_service:50051}") == "host.docker.internal:50051"


def test_expand_env_empty_value_falls_back(monkeypatch):
    monkeypatch.setenv("LLM_HEAVY_HOST", "")
    assert expand_env("${LLM_HEAVY_HOST:-llm_service:50051}") == "llm_service:50051"


def test_plain_endpoint_unchanged():
    assert expand_env("llm_service:50051") == "llm_service:50051"


def test_tier_endpoints_expand_but_config_keeps_template(monkeypatch):
    monkeypatch.setenv("LLM_STANDARD_HOST", "host.docker.internal:50061")
    cfg = RoutingConfig(tiers={
        "standard": TierConfig(endpoint="${LLM_STANDARD_HOST:-llm_service_standard:50051}"),
        "off": TierConfig(endpoint="${UNSET_TIER_HOST:-}", enabled=True),
    })
    assert cfg.get_tier_endpoints() == {"standard": "host.docker.internal:50061"}
    # Saving the config must not bake in the resolved host.
    assert "${LLM_STANDARD_HOST" in cfg.model_dump_json()
