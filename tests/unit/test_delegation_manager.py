"""
Unit tests for LIDM DelegationManager.

All LLM calls are mocked via a fake LLMClientPool so the tests
exercise classify → decompose → route → execute → aggregate → verify
logic without any gRPC or model inference.
"""

import json
import sys
import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from dataclasses import asdict

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

from orchestrator.delegation_manager import (
    SubTask,
    TaskDecomposition,
    DelegationManager,
)
from shared.clients.llm_client import LLMClientPool, LLMClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_pool(generate_side_effect=None):
    """Return a MagicMock pool with a controllable generate()."""
    pool = MagicMock(spec=LLMClientPool)
    pool.available_tiers = ["heavy", "standard"]

    if generate_side_effect:
        pool.generate.side_effect = generate_side_effect
    else:
        pool.generate.return_value = "mocked LLM response"

    # Default get_client returns a mock LLMClient
    mock_client = MagicMock(spec=LLMClient)
    mock_client.generate.return_value = "mocked client response"
    mock_client.generate_batch.return_value = {
        "responses": ["a", "a", "a"],
        "self_consistency_score": 0.9,
        "majority_answer": "a",
        "majority_count": 3,
    }
    pool.get_client.return_value = mock_client
    return pool


def _classify_json(task_type="general", capabilities=None, complexity=0.3):
    """Generate a JSON string that _classify_query expects the LLM to return."""
    return json.dumps({
        "task_type": task_type,
        "capabilities": capabilities or ["fast_response"],
        "complexity": complexity,
    })


def _decompose_json(items=None):
    """Generate a JSON array string for _decompose_task."""
    items = items or [
        {"id": "st_1", "instruction": "step one", "capabilities": ["coding"], "depends_on": []},
        {"id": "st_2", "instruction": "step two", "capabilities": ["analysis"], "depends_on": ["st_1"]},
    ]
    return json.dumps(items)


# ============================================================================
# Dataclass Tests
# ============================================================================

class TestSubTask:
    def test_defaults(self):
        t = SubTask(task_id="t1", instruction="do it", required_capabilities=["coding"])
        assert t.status == "pending"
        assert t.target_tier == ""
        assert t.depends_on == []
        assert t.result is None

    def test_serializable(self):
        t = SubTask(task_id="t1", instruction="x", required_capabilities=["math"])
        d = asdict(t)
        assert d["task_id"] == "t1"


class TestTaskDecomposition:
    def test_direct_strategy(self):
        td = TaskDecomposition(
            original_query="hi",
            sub_tasks=[SubTask(task_id="t1", instruction="hi", required_capabilities=[])],
            strategy="direct",
        )
        assert td.strategy == "direct"
        assert len(td.sub_tasks) == 1


# ============================================================================
# DelegationManager — classify / route
# ============================================================================

class TestAnalyzeAndRoute:
    """Test the main entry point: analyze_and_route."""

    def test_simple_query_direct_route(self):
        """Low complexity → single sub-task, 'direct' strategy."""
        pool = _mock_pool(generate_side_effect=[
            _classify_json("finance", ["finance"], 0.2),
        ])
        dm = DelegationManager(pool)
        result = dm.analyze_and_route("What is my balance?")

        assert result.strategy == "direct"
        assert len(result.sub_tasks) == 1
        assert result.sub_tasks[0].target_tier == "standard"

    def test_complex_query_decomposed(self):
        """High complexity → multiple sub-tasks, 'decompose' strategy."""
        pool = _mock_pool(generate_side_effect=[
            _classify_json("coding", ["coding", "analysis"], 0.8),
            _decompose_json(),
        ])
        dm = DelegationManager(pool)
        result = dm.analyze_and_route("Write a REST API and test it")

        assert result.strategy == "decompose"
        assert len(result.sub_tasks) == 2
        # Routing should have been resolved
        assert result.sub_tasks[0].target_tier != ""

    def test_classify_failure_falls_back(self):
        """If LLM returns garbage, classification defaults are used."""
        pool = _mock_pool(generate_side_effect=[
            "NOT VALID JSON",
        ])
        dm = DelegationManager(pool)
        result = dm.analyze_and_route("broken input")

        assert result.strategy == "direct"
        assert result.sub_tasks[0].target_tier == "standard"

    def test_single_capability_direct_even_if_high_complexity(self):
        """Single capability still yields direct strategy regardless of complexity."""
        pool = _mock_pool(generate_side_effect=[
            _classify_json("coding", ["coding"], 0.9),
        ])
        dm = DelegationManager(pool)
        result = dm.analyze_and_route("Write a function")

        assert result.strategy == "direct"
        assert result.sub_tasks[0].target_tier == "heavy"


# ============================================================================
# DelegationManager — execute
# ============================================================================

class TestExecuteDelegation:
    """Test dependency-ordered execution."""

    def test_single_task_execution(self):
        pool = _mock_pool()
        dm = DelegationManager(pool)

        sub = SubTask(task_id="t1", instruction="hello", required_capabilities=["finance"], target_tier="standard")
        decomp = TaskDecomposition(original_query="q", sub_tasks=[sub], strategy="direct")

        result = dm.execute_delegation(decomp)
        assert "t1" in result["completed"]
        assert sub.status == "completed"

    def test_dependent_tasks_execute_in_order(self):
        pool = _mock_pool()
        dm = DelegationManager(pool)

        t1 = SubTask(task_id="t1", instruction="first", required_capabilities=["coding"], target_tier="heavy")
        t2 = SubTask(task_id="t2", instruction="second", required_capabilities=["analysis"],
                      target_tier="heavy", depends_on=["t1"])
        decomp = TaskDecomposition(original_query="q", sub_tasks=[t1, t2], strategy="decompose")

        result = dm.execute_delegation(decomp)
        assert t1.status == "completed"
        assert t2.status == "completed"
        assert "t1" in result["completed"]
        assert "t2" in result["completed"]

    def test_deadlock_detection(self):
        """Circular dependencies should be detected and tasks marked failed."""
        pool = _mock_pool()
        dm = DelegationManager(pool)

        t1 = SubTask(task_id="t1", instruction="a", required_capabilities=[], target_tier="standard", depends_on=["t2"])
        t2 = SubTask(task_id="t2", instruction="b", required_capabilities=[], target_tier="standard", depends_on=["t1"])
        decomp = TaskDecomposition(original_query="q", sub_tasks=[t1, t2], strategy="decompose")

        result = dm.execute_delegation(decomp)
        assert t1.status == "failed"
        assert t2.status == "failed"

    def test_execution_failure_recorded(self):
        """When generate raises, sub-task status becomes 'failed'."""
        pool = _mock_pool()
        pool.generate.side_effect = RuntimeError("boom")
        dm = DelegationManager(pool)

        sub = SubTask(task_id="t1", instruction="x", required_capabilities=[], target_tier="standard")
        decomp = TaskDecomposition(original_query="q", sub_tasks=[sub], strategy="direct")

        dm.execute_delegation(decomp)
        assert sub.status == "failed"
        assert "Error" in (sub.result or "")


# ============================================================================
# DelegationManager — aggregate
# ============================================================================

class TestAggregateResults:
    """Test result synthesis."""

    def test_single_task_returns_result_directly(self):
        pool = _mock_pool()
        dm = DelegationManager(pool)

        sub = SubTask(task_id="t1", instruction="x", required_capabilities=[], result="answer42")
        decomp = TaskDecomposition(original_query="q", sub_tasks=[sub], strategy="direct")

        assert dm.aggregate_results("q", {}, decomp) == "answer42"

    def test_multi_task_calls_llm_synthesis(self):
        pool = _mock_pool()
        pool.generate.return_value = "synthesized answer"
        dm = DelegationManager(pool)

        t1 = SubTask(task_id="t1", instruction="a", required_capabilities=["coding"], result="part1")
        t2 = SubTask(task_id="t2", instruction="b", required_capabilities=["analysis"], result="part2")
        decomp = TaskDecomposition(original_query="big question", sub_tasks=[t1, t2], strategy="decompose")

        result = dm.aggregate_results("big question", {}, decomp)
        assert result == "synthesized answer"
        pool.generate.assert_called_once()

    def test_single_task_none_result_returns_empty(self):
        pool = _mock_pool()
        dm = DelegationManager(pool)

        sub = SubTask(task_id="t1", instruction="x", required_capabilities=[], result=None)
        decomp = TaskDecomposition(original_query="q", sub_tasks=[sub], strategy="direct")

        assert dm.aggregate_results("q", {}, decomp) == ""


# ============================================================================
# DelegationManager — verify
# ============================================================================

class TestVerifyResult:
    """Test cascading verification strategies."""

    def test_high_consistency_passes(self):
        """Self-consistency ≥ 0.6 → verified via self_consistency."""
        pool = _mock_pool()
        mock_client = pool.get_client.return_value
        mock_client.generate_batch.return_value = {
            "self_consistency_score": 0.8,
            "responses": ["ok"] * 3,
            "majority_answer": "ok",
            "majority_count": 3,
        }
        dm = DelegationManager(pool)

        result = dm.verify_result("q", "ok")
        assert result["verified"] is True
        assert result["method"] == "self_consistency"
        assert result["confidence"] == 0.8

    def test_low_consistency_upgrades_to_heavy(self):
        """Self-consistency < 0.6 → model_upgrade via heavy tier."""
        pool = _mock_pool()
        mock_std = MagicMock(spec=LLMClient)
        mock_std.generate_batch.return_value = {"self_consistency_score": 0.3}
        mock_heavy = MagicMock(spec=LLMClient)
        mock_heavy.generate.return_value = "better answer"

        def _get_client(tier):
            if tier == "standard":
                return mock_std
            if tier == "heavy":
                return mock_heavy
            return None

        pool.get_client.side_effect = _get_client
        dm = DelegationManager(pool)

        result = dm.verify_result("q", "bad answer")
        assert result["verified"] is True
        assert result["method"] == "model_upgrade"
        assert result["revised_answer"] == "better answer"

    def test_no_client_skips_verification(self):
        """If no standard client available, verification is skipped."""
        pool = _mock_pool()
        pool.get_client.return_value = None
        dm = DelegationManager(pool)

        result = dm.verify_result("q", "answer")
        assert result["verified"] is True
        assert result["method"] == "skip"

    def test_ultra_deep_verify_on_high_complexity(self):
        """When consistency low, no heavy, but ultra available + complexity > 0.8."""
        pool = _mock_pool()
        mock_std = MagicMock(spec=LLMClient)
        mock_std.generate_batch.return_value = {"self_consistency_score": 0.2}
        mock_ultra = MagicMock(spec=LLMClient)
        mock_ultra.generate.return_value = "deep verified"

        def _get_client(tier):
            if tier == "standard":
                return mock_std
            if tier == "ultra":
                return mock_ultra
            return None  # no heavy

        pool.get_client.side_effect = _get_client
        dm = DelegationManager(pool)

        result = dm.verify_result("q", "shaky answer", complexity=0.9)
        assert result["verified"] is True
        assert result["method"] == "airllm_deep"
        assert result["revised_answer"] == "deep verified"

    def test_verification_exception_returns_unverified(self):
        """If verification crashes, return unverified with original answer."""
        pool = _mock_pool()
        mock_client = pool.get_client.return_value
        mock_client.generate_batch.side_effect = RuntimeError("kaboom")
        dm = DelegationManager(pool)

        result = dm.verify_result("q", "original")
        assert result["verified"] is False
        assert result["method"] == "failed"
        assert result["revised_answer"] == "original"


# ============================================================================
# DelegationManager — private helpers
# ============================================================================

class TestClassifyQuery:
    """Test _classify_query (LLM-based JSON classification)."""

    def test_valid_json_parsed(self):
        pool = _mock_pool()
        pool.generate.return_value = _classify_json("math", ["math", "reasoning"], 0.6)
        dm = DelegationManager(pool)

        result = dm._classify_query("Solve x^2=4")
        assert result["task_type"] == "math"
        assert "math" in result["capabilities"]
        assert result["complexity"] == 0.6

    def test_invalid_json_returns_defaults(self):
        pool = _mock_pool()
        pool.generate.return_value = "not json at all"
        dm = DelegationManager(pool)

        result = dm._classify_query("anything")
        assert result["task_type"] == "general"
        assert result["complexity"] == 0.3


class TestDecomposeTask:
    """Test _decompose_task (LLM-based task decomposition)."""

    def test_valid_decomposition(self):
        pool = _mock_pool()
        pool.generate.return_value = _decompose_json([
            {"id": "st_1", "instruction": "parse data", "capabilities": ["analysis"], "depends_on": []},
            {"id": "st_2", "instruction": "generate chart", "capabilities": ["coding"], "depends_on": ["st_1"]},
        ])
        dm = DelegationManager(pool)

        tasks = dm._decompose_task("analyse and chart", {"capabilities": ["analysis", "coding"]})
        assert len(tasks) == 2
        assert tasks[1].depends_on == ["st_1"]

    def test_caps_at_five_subtasks(self):
        pool = _mock_pool()
        items = [{"id": f"st_{i}", "instruction": f"step {i}", "capabilities": ["coding"]} for i in range(10)]
        pool.generate.return_value = json.dumps(items)
        dm = DelegationManager(pool)

        tasks = dm._decompose_task("huge task", {"capabilities": ["coding"]})
        assert len(tasks) <= 5

    def test_invalid_json_returns_fallback(self):
        pool = _mock_pool()
        pool.generate.return_value = "broken"
        dm = DelegationManager(pool)

        tasks = dm._decompose_task("anything", {"capabilities": ["fast_response"]})
        assert len(tasks) == 1
        assert tasks[0].task_id == "st_fallback"


class TestResolveRouting:
    """Test _resolve_routing sets target_tier based on capabilities."""

    def test_sets_tier_for_each_task(self):
        pool = _mock_pool()
        dm = DelegationManager(pool)

        tasks = [
            SubTask(task_id="t1", instruction="x", required_capabilities=["coding"]),
            SubTask(task_id="t2", instruction="y", required_capabilities=["finance"]),
        ]
        dm._resolve_routing(tasks)
        assert tasks[0].target_tier == "heavy"
        assert tasks[1].target_tier == "standard"
