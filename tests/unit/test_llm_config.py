"""Tests for llm_service device / engine configuration (no llama_cpp needed)."""

import pytest

from llm_service.config import LLMServiceConfig, is_local_model_path, resolve_gpu_layers

ENV_KEYS = [
    "LLM_MODEL_PATH", "LLM_CTX_SIZE", "LLM_DEVICE", "LLM_GPU_LAYERS", "LLM_ENGINE", "LLM_TIER",
    "LLM_FLASH_ATTN", "LLM_KV_CACHE_TYPE", "LLM_N_UBATCH", "LLM_N_BATCH", "LLM_BATCH_SIZE", "LLM_MLOCK",
]


@pytest.fixture
def clean_env(monkeypatch):
    for key in ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    return monkeypatch


@pytest.mark.parametrize("device,expected", [("cpu", 0), ("gpu", -1), ("metal", -1), ("cuda", -1), ("auto", -1)])
def test_device_to_gpu_layers(device, expected):
    assert resolve_gpu_layers(device, None) == expected


def test_explicit_gpu_layers_win():
    assert resolve_gpu_layers("cpu", "20") == 20
    assert resolve_gpu_layers("gpu", "0") == 0
    assert resolve_gpu_layers("gpu", "") == -1


def test_from_env_defaults_are_docker_safe(clean_env):
    cfg = LLMServiceConfig.from_env()
    assert cfg.engine == "llamacpp"
    assert cfg.device == "auto"
    assert cfg.flash_attn is False
    assert cfg.kv_cache_type == "f16"
    assert cfg.mlock is False


def test_from_env_metal_heavy(clean_env):
    clean_env.setenv("LLM_MODEL_PATH", "llm_service/models/Qwen2.5-14B-Instruct-Q4_K_M.gguf")
    clean_env.setenv("LLM_DEVICE", "gpu")
    clean_env.setenv("LLM_TIER", "heavy")
    clean_env.setenv("LLM_FLASH_ATTN", "1")
    clean_env.setenv("LLM_KV_CACHE_TYPE", "q8_0")
    clean_env.setenv("LLM_N_BATCH", "2048")
    clean_env.setenv("LLM_MLOCK", "true")
    cfg = LLMServiceConfig.from_env()
    assert cfg.n_gpu_layers == -1
    assert cfg.tier == "heavy"
    assert cfg.flash_attn is True
    assert cfg.kv_cache_type == "q8_0"
    assert cfg.n_batch == 2048
    assert cfg.mlock is True
    assert cfg.n_ctx == 16_384  # registry auto-config


def test_cpu_device_disables_offload(clean_env):
    clean_env.setenv("LLM_DEVICE", "cpu")
    assert LLMServiceConfig.from_env().n_gpu_layers == 0


def _cfg(**kw):
    base = dict(model_path="mlx-community/Qwen2.5-3B-Instruct-4bit", engine="mlx", device="metal")
    base.update(kw)
    return LLMServiceConfig(**base)


def test_validate_rejects_unknown_device():
    with pytest.raises(ValueError, match="LLM_DEVICE"):
        _cfg(device="tpu").validate()


def test_validate_rejects_unknown_engine():
    with pytest.raises(ValueError, match="LLM_ENGINE"):
        _cfg(engine="vllm").validate()


def test_validate_rejects_quantized_kv_without_flash_attn():
    with pytest.raises(ValueError, match="FLASH_ATTN"):
        _cfg(engine="llamacpp", kv_cache_type="q8_0", flash_attn=False).validate()


def test_validate_rejects_gguf_on_mlx():
    with pytest.raises(ValueError, match="gguf"):
        _cfg(model_path="models/x.gguf").validate()


def test_validate_accepts_hf_repo_id_without_local_file():
    _cfg().validate()  # resolved by mlx_lm, so no FileNotFoundError


def test_validate_missing_local_file():
    with pytest.raises(FileNotFoundError):
        _cfg(engine="llamacpp", model_path="models/missing.gguf").validate()


@pytest.mark.parametrize("path,local", [
    ("mlx-community/Qwen2.5-3B-Instruct-4bit", False),
    ("llm_service/models/x.gguf", True),
    ("./models/x.gguf", True),
    ("/abs/dir/model", True),
])
def test_is_local_model_path(path, local):
    assert is_local_model_path(path) is local
