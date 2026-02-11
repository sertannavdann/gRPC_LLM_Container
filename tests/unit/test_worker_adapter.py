"""
Unit tests for LIDM worker adapters.

Tests LLMServiceAdapter (current) and RemoteWorkerAdapter (placeholder).
"""

import sys
import pytest
from unittest.mock import MagicMock

# Pre-mock the entire OpenTelemetry + observability chain
_otel_mods = [
    "opentelemetry", "opentelemetry.trace", "opentelemetry.metrics",
    "opentelemetry.sdk", "opentelemetry.sdk.trace", "opentelemetry.sdk.trace.export",
    "opentelemetry.sdk.metrics", "opentelemetry.sdk.metrics.export",
    "opentelemetry.sdk.resources",
    "opentelemetry.exporter", "opentelemetry.exporter.otlp",
    "opentelemetry.exporter.otlp.proto", "opentelemetry.exporter.otlp.proto.grpc",
    "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
    "opentelemetry.exporter.otlp.proto.grpc.metric_exporter",
    "opentelemetry.exporter.prometheus",
    "opentelemetry.instrumentation", "opentelemetry.instrumentation.grpc",
    "shared.observability", "shared.observability.setup",
    "shared.observability.grpc_interceptor",
]
for _mod in _otel_mods:
    sys.modules.setdefault(_mod, MagicMock())

from orchestrator.worker_adapter import (
    LLMServiceAdapter,
    RemoteWorkerAdapter,
)
from shared.clients.llm_client import LLMClientPool


# ---------------------------------------------------------------------------
# LLMServiceAdapter
# ---------------------------------------------------------------------------

class TestLLMServiceAdapter:
    """Test the adapter that routes through LLMClientPool."""

    def _make_adapter(self, generate_return="ok"):
        pool = MagicMock(spec=LLMClientPool)
        pool.generate.return_value = generate_return
        return LLMServiceAdapter(pool), pool

    def test_execute_returns_completed(self):
        adapter, pool = self._make_adapter("result text")
        out = adapter.execute("t1", "do something")
        assert out["status"] == "completed"
        assert out["result"] == "result text"

    def test_tier_forwarded(self):
        adapter, pool = self._make_adapter()
        adapter.execute("t1", "inst", tier="heavy")
        pool.generate.assert_called_once_with(prompt="inst", tier="heavy", max_tokens=1024)

    def test_context_prepended_to_prompt(self):
        adapter, pool = self._make_adapter()
        adapter.execute("t1", "do it", context="prior result")
        call_kwargs = pool.generate.call_args
        prompt_sent = call_kwargs.kwargs.get("prompt") or call_kwargs[1].get("prompt") or call_kwargs[0][0] if call_kwargs[0] else ""
        # The adapter prepends context
        assert "prior result" in (call_kwargs.kwargs.get("prompt", "") or "")

    def test_exception_returns_failed(self):
        adapter, pool = self._make_adapter()
        pool.generate.side_effect = RuntimeError("network down")
        out = adapter.execute("t1", "inst")
        assert out["status"] == "failed"
        assert "Error" in out["result"]

    def test_max_tokens_configurable(self):
        adapter, pool = self._make_adapter()
        adapter.execute("t1", "inst", max_tokens=256)
        pool.generate.assert_called_once_with(prompt="inst", tier="standard", max_tokens=256)


# ---------------------------------------------------------------------------
# RemoteWorkerAdapter
# ---------------------------------------------------------------------------

class TestRemoteWorkerAdapter:
    """Test the placeholder remote worker adapter."""

    def test_no_endpoints_returns_failed(self):
        adapter = RemoteWorkerAdapter()
        out = adapter.execute("t1", "do something")
        assert out["status"] == "failed"
        assert "No remote workers" in out["result"]

    def test_with_endpoints_returns_not_implemented(self):
        adapter = RemoteWorkerAdapter(worker_endpoints={"general": "worker1:8080"})
        out = adapter.execute("t1", "do something")
        assert out["status"] == "not_implemented"

    def test_capability_forwarded(self):
        adapter = RemoteWorkerAdapter(worker_endpoints={"coding": "worker2:8080"})
        out = adapter.execute("t1", "code it", capability="coding")
        assert out["capability"] == "coding"
