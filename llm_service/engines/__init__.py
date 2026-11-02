"""Inference engines. ``create_engine`` picks one from LLMServiceConfig.engine."""

from .base import Engine, GenParams, GenStats


def create_engine(config) -> Engine:
    name = config.engine
    if name == "llamacpp":
        from .llamacpp import LlamaCppEngine
        return LlamaCppEngine(config)
    if name == "mlx":
        from .mlx_engine import MlxEngine
        return MlxEngine(config)
    raise ValueError(f"Unknown LLM_ENGINE {name!r}; expected 'llamacpp' or 'mlx'")


__all__ = ["Engine", "GenParams", "GenStats", "create_engine"]
