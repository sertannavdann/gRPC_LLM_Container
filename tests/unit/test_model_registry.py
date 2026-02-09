"""
Unit tests for the model registry.

Tests auto-detection of model specs from filenames and the
auto_configure helper that provides n_ctx / max_tokens / temperature.
"""

import pytest
from llm_service.model_registry import (
    MODEL_SPECS,
    ModelSpec,
    resolve_model_spec,
    auto_configure,
)


class TestModelRegistry:
    """Tests for llm_service/model_registry.py"""

    def test_known_model_mistral(self):
        spec = resolve_model_spec("./models/Mistral-Small-24B-Instruct-2501.Q8_0.gguf")
        assert spec is not None
        assert spec.recommended_ctx == 16_384
        assert spec.max_tokens == 2048
        assert spec.temperature == 0.15

    def test_known_model_qwen14b(self):
        spec = resolve_model_spec("models/Qwen2.5-14B-Instruct-Q4_K.gguf")
        assert spec is not None
        assert spec.recommended_ctx == 16_384
        assert spec.context_window == 131_072

    def test_known_model_qwen05b(self):
        spec = resolve_model_spec("/some/path/qwen2.5-0.5b-instruct-q5_k_m.gguf")
        assert spec is not None
        assert spec.recommended_ctx == 2048
        assert spec.max_tokens == 512

    def test_unknown_model_returns_none(self):
        spec = resolve_model_spec("models/totally-unknown-model.gguf")
        assert spec is None

    def test_auto_configure_known(self):
        cfg = auto_configure("./models/Mistral-Small-24B-Instruct-2501.Q8_0.gguf")
        assert cfg["n_ctx"] == 16_384
        assert cfg["max_tokens"] == 2048
        assert cfg["default_temperature"] == 0.15

    def test_auto_configure_unknown_defaults(self):
        cfg = auto_configure("models/unknown.gguf")
        assert cfg["n_ctx"] == 4096
        assert cfg["max_tokens"] == 1024
        assert cfg["default_temperature"] == 0.7

    def test_auto_configure_override_ctx(self):
        cfg = auto_configure(
            "./models/Mistral-Small-24B-Instruct-2501.Q8_0.gguf",
            override_ctx=8192,
        )
        assert cfg["n_ctx"] == 8192  # explicit override wins

    def test_all_specs_have_required_fields(self):
        for filename, spec in MODEL_SPECS.items():
            assert isinstance(spec, ModelSpec)
            assert spec.name, f"Missing name for {filename}"
            assert spec.context_window > 0
            assert spec.recommended_ctx > 0
            assert spec.max_tokens > 0
            assert 0 <= spec.temperature <= 2.0
