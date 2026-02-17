"""Unit tests for orchestrator config provider env parsing."""

from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path


CONFIG_PATH = Path(__file__).resolve().parents[2] / "orchestrator" / "config.py"
_SPEC = spec_from_file_location("orchestrator_config_module", CONFIG_PATH)
_CONFIG_MODULE = module_from_spec(_SPEC)
assert _SPEC and _SPEC.loader
_SPEC.loader.exec_module(_CONFIG_MODULE)
OrchestratorConfig = _CONFIG_MODULE.OrchestratorConfig


class TestOrchestratorConfigProviderEnv:
    def test_nvidia_defaults_and_overrides(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "nvidia")
        monkeypatch.setenv("NIM_API_KEY", "nim-key")
        monkeypatch.setenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        monkeypatch.setenv("LLM_PROVIDER_TOP_P", "0.95")
        monkeypatch.setenv("LLM_PROVIDER_THINKING", "true")
        monkeypatch.setenv("LLM_PROVIDER_MAX_TOKENS", "16384")

        cfg = OrchestratorConfig.from_env()

        assert cfg.provider_type == "nvidia"
        assert cfg.provider_api_key == "nim-key"
        assert cfg.provider_base_url == "https://integrate.api.nvidia.com/v1"
        assert cfg.provider_model == "moonshotai/kimi-k2.5"
        assert cfg.provider_top_p == 0.95
        assert cfg.provider_thinking is True
        assert cfg.provider_max_tokens == 16384

    def test_provider_thinking_false(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "nvidia")
        monkeypatch.setenv("NIM_API_KEY", "nim-key")
        monkeypatch.setenv("LLM_PROVIDER_THINKING", "false")

        cfg = OrchestratorConfig.from_env()
        assert cfg.provider_thinking is False

    def test_empty_provider_env_values_fallback(self, monkeypatch):
        monkeypatch.setenv("LLM_PROVIDER", "nvidia")
        monkeypatch.setenv("NIM_API_KEY", "nim-key")
        monkeypatch.setenv("LLM_PROVIDER_TOP_P", "")
        monkeypatch.setenv("LLM_PROVIDER_THINKING", "")

        cfg = OrchestratorConfig.from_env()

        assert cfg.provider_top_p == 0.95
        assert cfg.provider_thinking is None
