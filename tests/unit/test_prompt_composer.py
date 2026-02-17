"""
Tests for auto-prompt composition and soul loading.

Validates:
- Soul.md file loading and caching
- StageContext creation
- Compose function output structure
- Stage-specific context interpolation
"""

import pytest
import json
from pathlib import Path

from shared.agents.prompt_composer import (
    compose,
    load_soul,
    clear_soul_cache,
    StageContext,
)


class TestLoadSoul:
    """Test soul.md loading and caching."""

    def test_load_builder_soul(self):
        """Builder soul loads successfully and contains Mission."""
        soul = load_soul("builder")
        assert isinstance(soul, str)
        assert len(soul) > 100
        assert "Mission" in soul
        assert "Scope" in soul

    def test_load_tester_soul(self):
        """Tester soul loads successfully and contains Mission."""
        soul = load_soul("tester")
        assert isinstance(soul, str)
        assert len(soul) > 100
        assert "Mission" in soul
        assert "Test Taxonomy" in soul

    def test_load_monitor_soul(self):
        """Monitor soul loads successfully and contains Mission."""
        soul = load_soul("monitor")
        assert isinstance(soul, str)
        assert len(soul) > 100
        assert "Mission" in soul
        assert "fidelity" in soul.lower()

    def test_load_nonexistent_soul_raises(self):
        """Loading non-existent soul raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_soul("nonexistent_agent")

    def test_soul_caching(self):
        """Souls are cached after first load."""
        clear_soul_cache()

        # First load
        soul1 = load_soul("builder")

        # Second load should return same object from cache
        soul2 = load_soul("builder")

        assert soul1 is soul2  # Same object, not just equal content


class TestStageContext:
    """Test StageContext dataclass creation."""

    def test_minimal_context(self):
        """StageContext can be created with minimal fields."""
        ctx = StageContext(
            stage="scaffold",
            attempt=1,
            intent="Build a weather adapter",
        )
        assert ctx.stage == "scaffold"
        assert ctx.attempt == 1
        assert ctx.intent == "Build a weather adapter"
        assert ctx.constraints is None
        assert ctx.prior_artifacts is None
        assert ctx.repair_hints is None
        assert ctx.policy_profile is None
        assert ctx.manifest_snapshot is None

    def test_full_context(self):
        """StageContext can be created with all fields."""
        ctx = StageContext(
            stage="repair",
            attempt=3,
            intent="Fix auth error",
            constraints={"max_files": 5},
            prior_artifacts={"scaffold": {"files": ["adapter.py"]}},
            repair_hints=["Fix import error", "Add error handling"],
            policy_profile="strict",
            manifest_snapshot={"name": "weather", "version": "1.0.0"},
        )
        assert ctx.stage == "repair"
        assert ctx.attempt == 3
        assert ctx.intent == "Fix auth error"
        assert ctx.constraints == {"max_files": 5}
        assert len(ctx.repair_hints) == 2
        assert ctx.policy_profile == "strict"


class TestCompose:
    """Test compose function for different stages."""

    def test_compose_scaffold_stage(self):
        """Compose includes soul + stage + intent for scaffold."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="scaffold",
            attempt=1,
            intent="Build OpenWeather adapter",
        )

        prompt = compose(soul, ctx)

        # Should contain soul content
        assert "Mission" in prompt
        assert "Scope" in prompt

        # Should contain stage header
        assert "Current Stage: scaffold" in prompt
        assert "Attempt 1" in prompt

        # Should contain intent
        assert "Intent" in prompt
        assert "Build OpenWeather adapter" in prompt

    def test_compose_implement_stage_with_prior_artifacts(self):
        """Compose includes prior artifacts for implement stage."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="implement",
            attempt=1,
            intent="Implement weather fetch",
            prior_artifacts={"scaffold_files": ["adapter.py", "manifest.json"]},
        )

        prompt = compose(soul, ctx)

        assert "Current Stage: implement" in prompt
        assert "Prior Stage Artifacts" in prompt
        assert "scaffold_files" in prompt

    def test_compose_repair_stage_with_hints(self):
        """Compose includes repair hints for repair stage."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="repair",
            attempt=2,
            intent="Fix validation errors",
            repair_hints=[
                "Import error: module 'requests' not found",
                "Schema validation failed: missing 'transform' method",
            ],
        )

        prompt = compose(soul, ctx)

        assert "Current Stage: repair" in prompt
        assert "Attempt 2" in prompt
        assert "Repair Hints" in prompt
        assert "Import error" in prompt
        assert "Schema validation failed" in prompt

    def test_compose_test_stage(self):
        """Compose works for test stage."""
        soul = load_soul("tester")
        ctx = StageContext(
            stage="test",
            attempt=1,
            intent="Generate test suite",
        )

        prompt = compose(soul, ctx)

        assert "Current Stage: test" in prompt
        assert "Mission" in prompt
        assert "Generate test suite" in prompt

    def test_compose_with_constraints(self):
        """Compose includes constraints section."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="scaffold",
            attempt=1,
            intent="Build adapter",
            constraints={"max_files": 3, "timeout": 30},
        )

        prompt = compose(soul, ctx)

        assert "Constraints" in prompt
        assert "max_files" in prompt
        assert "timeout" in prompt

    def test_compose_with_output_schema(self):
        """Compose includes output schema section."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="implement",
            attempt=1,
            intent="Build adapter",
        )

        schema = {
            "type": "object",
            "properties": {
                "stage": {"type": "string"},
                "module": {"type": "object"},
            },
        }

        prompt = compose(soul, ctx, output_schema=schema)

        assert "Required Output Schema" in prompt
        assert "type" in prompt
        assert "properties" in prompt

    def test_compose_with_policy_profile(self):
        """Compose includes policy profile."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="scaffold",
            attempt=1,
            intent="Build adapter",
            policy_profile="strict",
        )

        prompt = compose(soul, ctx)

        assert "Policy Profile" in prompt
        assert "strict" in prompt

    def test_compose_with_manifest_snapshot(self):
        """Compose includes manifest snapshot for updates."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="implement",
            attempt=1,
            intent="Update adapter",
            manifest_snapshot={"name": "weather", "version": "1.0.0"},
        )

        prompt = compose(soul, ctx)

        assert "Current Module Manifest" in prompt
        assert "weather" in prompt
        assert "version" in prompt


class TestComposeEdgeCases:
    """Test edge cases and error handling."""

    def test_compose_empty_repair_hints(self):
        """Compose handles empty repair hints list."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="repair",
            attempt=1,
            intent="Fix errors",
            repair_hints=[],
        )

        prompt = compose(soul, ctx)

        # Should not crash, but repair hints section should be minimal or absent
        assert "Current Stage: repair" in prompt

    def test_compose_none_values(self):
        """Compose handles None values gracefully."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="scaffold",
            attempt=1,
            intent="Build adapter",
            constraints=None,
            prior_artifacts=None,
            repair_hints=None,
            policy_profile=None,
            manifest_snapshot=None,
        )

        prompt = compose(soul, ctx)

        # Should not crash
        assert "Mission" in prompt
        assert "Current Stage: scaffold" in prompt

    def test_compose_output_length_reasonable(self):
        """Composed prompts are not excessively long."""
        soul = load_soul("builder")
        ctx = StageContext(
            stage="implement",
            attempt=1,
            intent="Build complex adapter with many features",
            constraints={"max_files": 10},
            prior_artifacts={"scaffold": "data"},
        )

        prompt = compose(soul, ctx)

        # Should be long but not absurdly so (< 50KB for typical case)
        assert len(prompt) < 50_000
