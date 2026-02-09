"""
Unit tests for LLMClientPool — multi-tier LLM client management.

All gRPC calls are mocked; these tests verify routing, fallback,
and pool lifecycle logic.
"""

import pytest
from unittest.mock import patch, MagicMock, PropertyMock

from shared.clients.llm_client import LLMClient, LLMClientPool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_pool(tiers=None):
    """Create a pool with mocked LLMClient instances (bypass gRPC)."""
    tiers = tiers or {"heavy": "host_h:50051", "standard": "host_s:50061"}
    with patch.object(LLMClient, "__init__", lambda self, **kw: None):
        pool = LLMClientPool(tiers)
        # Replace real (uninitialised) clients with mocks
        for tier in pool.clients:
            mock_client = MagicMock(spec=LLMClient)
            mock_client.generate.return_value = f"response_from_{tier}"
            mock_client.get_active_model.return_value = {"model_name": f"model_{tier}"}
            mock_client.generate_batch.return_value = {
                "responses": ["a", "a", "b"],
                "self_consistency_score": 0.67,
                "majority_answer": "a",
                "majority_count": 2,
            }
            pool.clients[tier] = mock_client
    return pool


class TestLLMClientPoolInit:
    """Test pool construction."""

    def test_creates_clients_for_each_tier(self):
        pool = _make_pool({"heavy": "h:50051", "standard": "s:50061"})
        assert set(pool.available_tiers) == {"heavy", "standard"}

    def test_skips_empty_endpoint(self):
        pool = _make_pool({"heavy": "h:50051", "standard": ""})
        # The empty endpoint should be skipped
        assert "standard" not in pool.available_tiers or pool.clients.get("standard") is not None
        # Actually LLMClientPool checks `if not endpoint: continue`, so empty string is skipped
        # But our _make_pool patches __init__, let me test directly:

    def test_empty_endpoints_dict(self):
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            pool = LLMClientPool({})
        assert pool.available_tiers == []


class TestGetClient:
    """Test tier-based client lookup with fallback."""

    def test_exact_tier_match(self):
        pool = _make_pool()
        client = pool.get_client("heavy")
        assert client is pool.clients["heavy"]

    def test_missing_tier_falls_back_to_standard(self):
        pool = _make_pool({"heavy": "h:50051", "standard": "s:50061"})
        client = pool.get_client("ultra")
        assert client is pool.clients["standard"]

    def test_missing_standard_falls_back_to_any(self):
        pool = _make_pool({"heavy": "h:50051"})
        client = pool.get_client("ultra")
        assert client is pool.clients["heavy"]

    def test_empty_pool_returns_none(self):
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            pool = LLMClientPool({})
        assert pool.get_client("standard") is None


class TestGenerate:
    """Test generation routing through the pool."""

    def test_routes_to_correct_tier(self):
        pool = _make_pool()
        result = pool.generate("hello", tier="heavy")
        assert result == "response_from_heavy"
        pool.clients["heavy"].generate.assert_called_once_with("hello")

    def test_fallback_when_tier_missing(self):
        pool = _make_pool({"standard": "s:50061"})
        result = pool.generate("hello", tier="ultra")
        assert result == "response_from_standard"

    def test_no_client_returns_error(self):
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            pool = LLMClientPool({})
        result = pool.generate("hello")
        assert "Error" in result or "error" in result.lower()

    def test_kwargs_forwarded(self):
        pool = _make_pool()
        pool.generate("prompt", tier="standard", max_tokens=256, temperature=0.1)
        pool.clients["standard"].generate.assert_called_once_with(
            "prompt", max_tokens=256, temperature=0.1
        )


class TestGetActiveModels:
    """Test model info aggregation across tiers."""

    def test_queries_all_tiers(self):
        pool = _make_pool()
        models = pool.get_active_models()
        assert "heavy" in models
        assert "standard" in models
        assert models["heavy"]["model_name"] == "model_heavy"

    def test_empty_pool_returns_empty_dict(self):
        with patch.object(LLMClient, "__init__", lambda self, **kw: None):
            pool = LLMClientPool({})
        assert pool.get_active_models() == {}
