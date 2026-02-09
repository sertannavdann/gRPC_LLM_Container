"""
Model registry for automatic configuration based on GGUF model files.

Maps known model filenames to their optimal inference parameters so the
LLM service can auto-configure n_ctx, temperature, and max_tokens based
on which model is loaded — no manual tuning required.

LIDM: Extended with capabilities, tier, and backend fields for
multi-instance routing and delegation.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Dict, List, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ModelSpec:
    """Optimal inference parameters for a specific model."""

    name: str
    context_window: int  # max n_ctx tokens
    recommended_ctx: int  # practical n_ctx for GGUF quantised runs
    max_tokens: int  # default generation cap
    temperature: float  # recommended default
    description: str = ""
    capabilities: Tuple[str, ...] = ()
    tier: str = "standard"  # heavy, standard, light, micro, ultra
    backend: str = "llama-cpp"  # llama-cpp, airllm


# ── Known models ──────────────────────────────────────────────────────
MODEL_SPECS: Dict[str, ModelSpec] = {
    "Mistral-Small-24B-Instruct-2501.Q8_0.gguf": ModelSpec(
        name="Mistral-Small-24B-Instruct",
        context_window=32_768,
        recommended_ctx=16_384,
        max_tokens=2048,
        temperature=0.15,
        description="Mistral Small 24B Q8 – strong reasoning, 32K ctx",
        capabilities=("reasoning", "coding", "analysis", "verification"),
        tier="heavy",
        backend="llama-cpp",
    ),
    "Qwen2.5-14B-Instruct-Q4_K.gguf": ModelSpec(
        name="Qwen2.5-14B-Instruct",
        context_window=131_072,
        recommended_ctx=16_384,
        max_tokens=2048,
        temperature=0.7,
        description="Qwen 2.5 14B Q4_K – 128K ctx, recommended ≤16K GGUF",
        capabilities=("coding", "multilingual", "reasoning", "math", "finance"),
        tier="standard",
        backend="llama-cpp",
    ),
    "qwen2.5-3b-instruct-q5_k_m.gguf": ModelSpec(
        name="Qwen2.5-3B-Instruct",
        context_window=32_768,
        recommended_ctx=4096,
        max_tokens=1024,
        temperature=0.7,
        description="Qwen 2.5 3B Q5_K_M – lightweight, 32K ctx",
        capabilities=("routing", "classification", "fast_response"),
        tier="light",
        backend="llama-cpp",
    ),
    "qwen2.5-0.5b-instruct-q5_k_m.gguf": ModelSpec(
        name="Qwen2.5-0.5B-Instruct",
        context_window=4096,
        recommended_ctx=2048,
        max_tokens=512,
        temperature=0.7,
        description="Qwen 2.5 0.5B Q5_K_M – minimal footprint",
        capabilities=("routing", "classification", "extraction"),
        tier="micro",
        backend="llama-cpp",
    ),
    # AirLLM model (HuggingFace safetensors, not GGUF)
    "Llama-3.1-70B-Instruct": ModelSpec(
        name="Llama-3.1-70B-Instruct",
        context_window=131_072,
        recommended_ctx=8192,
        max_tokens=2048,
        temperature=0.7,
        description="Llama 3.1 70B – layer-streaming via AirLLM, ~5-10 tok/s",
        capabilities=("reasoning", "verification", "analysis", "deep_research"),
        tier="ultra",
        backend="airllm",
    ),
}


def resolve_model_spec(model_path: str) -> Optional[ModelSpec]:
    """
    Look up inference specs for a model file.

    Matches by filename (last path segment).  Falls back to ``None`` if
    the model is unknown so the caller can use its own defaults.
    """
    filename = Path(model_path).name
    spec = MODEL_SPECS.get(filename)
    if spec:
        logger.info(f"Model registry matched: {filename} → {spec.name} "
                     f"(ctx={spec.recommended_ctx}, max_tok={spec.max_tokens}, "
                     f"tier={spec.tier})")
    else:
        logger.warning(f"Model '{filename}' not in registry – using caller defaults")
    return spec


def auto_configure(model_path: str, *, override_ctx: Optional[int] = None) -> dict:
    """
    Return a configuration dict suitable for merging into LLMServiceConfig.

    If the model is known, returns recommended n_ctx, max_tokens and
    temperature.  Explicit ``override_ctx`` takes priority.
    """
    spec = resolve_model_spec(model_path)
    if spec is None:
        return {
            "n_ctx": override_ctx or 4096,
            "max_tokens": 1024,
            "default_temperature": 0.7,
        }

    return {
        "n_ctx": override_ctx or spec.recommended_ctx,
        "max_tokens": spec.max_tokens,
        "default_temperature": spec.temperature,
    }


def find_models_by_capability(capability: str) -> List[ModelSpec]:
    """Return all models that have the given capability, sorted by tier priority."""
    tier_order = {"ultra": 0, "heavy": 1, "standard": 2, "light": 3, "micro": 4}
    matches = [
        spec for spec in MODEL_SPECS.values()
        if capability in spec.capabilities
    ]
    matches.sort(key=lambda s: tier_order.get(s.tier, 99))
    return matches


def get_best_model_for_task(required_capabilities: List[str]) -> Optional[ModelSpec]:
    """
    Find the best model that satisfies all required capabilities.

    Returns the highest-tier model that has all capabilities.
    Falls back to the model covering the most capabilities.
    """
    tier_order = {"ultra": 0, "heavy": 1, "standard": 2, "light": 3, "micro": 4}

    best = None
    best_score = -1

    for spec in MODEL_SPECS.values():
        covered = sum(1 for cap in required_capabilities if cap in spec.capabilities)
        if covered == 0:
            continue

        # Prefer full coverage, then higher tier
        tier_rank = 10 - tier_order.get(spec.tier, 5)
        score = (covered * 100) + tier_rank

        if score > best_score:
            best_score = score
            best = spec

    return best


def list_all_models() -> List[ModelSpec]:
    """Return all registered models."""
    return list(MODEL_SPECS.values())
