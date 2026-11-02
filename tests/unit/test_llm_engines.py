"""Tests for llm_service engines without loading a real model."""

import sys
import types

import pytest

from llm_service.config import LLMServiceConfig
from llm_service.engines import create_engine
from llm_service.engines.llamacpp import LlamaCppEngine, build_llama_kwargs, detect_device


def test_factory_picks_engine_by_name():
    assert create_engine(LLMServiceConfig(engine="llamacpp")).name == "llamacpp"
    assert create_engine(LLMServiceConfig(engine="mlx")).name == "mlx"
    with pytest.raises(ValueError, match="LLM_ENGINE"):
        create_engine(LLMServiceConfig(engine="nope"))


@pytest.mark.parametrize("layers,offload,platform,expected", [
    (-1, True, "darwin", "metal"),
    (-1, True, "linux", "cuda"),
    (-1, False, "darwin", "cpu"),
    (0, True, "darwin", "cpu"),
])
def test_detect_device(layers, offload, platform, expected):
    assert detect_device(layers, offload, platform) == expected


def test_metal_kwargs_include_quantized_kv():
    fake = types.SimpleNamespace(GGML_TYPE_Q8_0=8)
    cfg = LLMServiceConfig(model_path="m.gguf", n_gpu_layers=-1, flash_attn=True,
                           kv_cache_type="q8_0", n_batch=2048, n_ubatch=512, mlock=True)
    kw = build_llama_kwargs(cfg, fake)
    assert kw["n_gpu_layers"] == -1
    assert kw["flash_attn"] is True
    assert kw["type_k"] == kw["type_v"] == 8
    assert kw["n_batch"] == 2048 and kw["n_ubatch"] == 512
    assert kw["use_mlock"] is True


def test_cpu_kwargs_leave_kv_default_and_clamp_ubatch():
    cfg = LLMServiceConfig(model_path="m.gguf", n_gpu_layers=0, n_batch=256, n_ubatch=512)
    kw = build_llama_kwargs(cfg, types.SimpleNamespace())
    assert "type_k" not in kw and "type_v" not in kw
    assert kw["n_gpu_layers"] == 0
    assert kw["n_ubatch"] == 256


def test_llamacpp_load_passes_metal_kwargs(monkeypatch):
    captured = {}

    class FakeLlama:
        def __init__(self, **kwargs):
            captured.update(kwargs)

    fake = types.ModuleType("llama_cpp")
    fake.Llama = FakeLlama
    fake.LlamaGrammar = types.SimpleNamespace(from_string=lambda *a, **k: "grammar")
    fake.llama_supports_gpu_offload = lambda: True
    fake.GGML_TYPE_Q8_0 = 8
    monkeypatch.setitem(sys.modules, "llama_cpp", fake)
    monkeypatch.setattr(sys, "platform", "darwin")

    engine = LlamaCppEngine(LLMServiceConfig(model_path="m.gguf", n_gpu_layers=-1,
                                             flash_attn=True, kv_cache_type="q8_0"))
    engine.load()
    assert engine.effective_device == "metal"
    assert captured["n_gpu_layers"] == -1 and captured["type_k"] == 8


def test_mlx_engine_reports_missing_package(monkeypatch):
    monkeypatch.setitem(sys.modules, "mlx_lm", None)  # makes `import mlx_lm` raise ImportError
    engine = create_engine(LLMServiceConfig(engine="mlx", model_path="mlx-community/x"))
    with pytest.raises(RuntimeError, match="mlx-lm"):
        engine.load()
