"""
Configuration for LLM Service.

Centralizes all LLM service settings including model paths, inference parameters,
and service configuration. Supports environment variable overrides.
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

VALID_DEVICES = ("auto", "cpu", "gpu", "metal", "cuda")
VALID_ENGINES = ("llamacpp", "mlx")
VALID_KV_TYPES = ("f16", "q8_0", "q4_0")


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def resolve_gpu_layers(device: str, explicit: Optional[str]) -> int:
    """
    Decide how many layers to offload to the GPU.

    An explicit LLM_GPU_LAYERS value always wins. Otherwise ``cpu`` means 0
    and every other device means -1 (all layers). A llama.cpp build without
    GPU support ignores ``n_gpu_layers``, so -1 is safe on any host.
    """
    if explicit is not None and str(explicit).strip() != "":
        return int(explicit)
    return 0 if device == "cpu" else -1


def is_local_model_path(model_path: str) -> bool:
    """True for a filesystem path; False for a Hugging Face repo id like ``org/name``."""
    if model_path.startswith((".", "/", "~")) or model_path.endswith(".gguf"):
        return True
    return Path(model_path).exists() or model_path.count("/") != 1


@dataclass
class LLMServiceConfig:
    """
    Configuration for LLM Service.
    
    Attributes:
        model_path: Path to GGUF model file
        n_ctx: Context window size (tokens)
        n_threads: CPU threads for inference
        n_batch: Batch size for prompt processing
        max_tokens: Maximum tokens per generation (hard limit)
        default_temperature: Default temperature for sampling
        host: gRPC server host
        port: gRPC server port
        max_workers: ThreadPoolExecutor workers
        verbose: Enable verbose model logging
        engine: Inference engine (llamacpp | mlx)
        device: Requested device (auto | cpu | gpu | metal | cuda)
        n_gpu_layers: Layers offloaded to the GPU (-1 = all, 0 = CPU only)
        tier: LIDM tier this process serves (overrides the registry tier)
        flash_attn: Enable flash attention (llama.cpp; required for quantized KV)
        kv_cache_type: KV cache type (f16 | q8_0 | q4_0; llama.cpp only)
        n_ubatch: Physical micro-batch size for prompt processing (llama.cpp)
        mlock: Lock model weights in RAM so they are never paged out
    """
    # Model configuration
    model_path: str = "./models/qwen2.5-3b-instruct-q5_k_m.gguf"
    n_ctx: int = 16384
    n_threads: int = 4
    n_batch: int = 512
    verbose: bool = False

    # Engine / device configuration
    engine: str = "llamacpp"
    device: str = "auto"
    n_gpu_layers: int = 0
    tier: str = ""
    flash_attn: bool = False
    kv_cache_type: str = "f16"
    n_ubatch: int = 512
    mlock: bool = False

    # Generation defaults
    max_tokens: int = 2048
    default_temperature: float = 0.15
    
    # Service configuration
    host: str = "[::]"
    port: int = 50051
    max_workers: int = 4
    
    @classmethod
    def from_env(cls) -> "LLMServiceConfig":
        """
        Load configuration from environment variables.

        When LLM_CTX_SIZE / LLM_MAX_TOKENS / LLM_TEMPERATURE are **not** set
        explicitly the model_registry auto-configures them from the model
        filename.  Explicit env-vars always win.

        Environment variables:
            LLM_MODEL_PATH: Path to GGUF model
            LLM_CTX_SIZE: Context window size (auto if unset)
            LLM_THREADS: CPU threads
            LLM_BATCH_SIZE: Batch size
            LLM_MAX_TOKENS: Max generation tokens (auto if unset)
            LLM_TEMPERATURE: Default temperature (auto if unset)
            LLM_HOST: gRPC host
            LLM_PORT: gRPC port
            LLM_MAX_WORKERS: Max workers
            LLM_VERBOSE: Enable verbose logging (1/0)
            LLM_ENGINE: llamacpp (default) | mlx
            LLM_DEVICE: auto (default) | cpu | gpu | metal | cuda
            LLM_GPU_LAYERS: explicit layer count (-1 = all); overrides LLM_DEVICE
            LLM_TIER: tier label reported by GetActiveModel
            LLM_FLASH_ATTN, LLM_KV_CACHE_TYPE, LLM_N_UBATCH, LLM_MLOCK: llama.cpp runtime knobs

        Returns:
            LLMServiceConfig: Configuration instance
        """
        try:
            from llm_service.model_registry import auto_configure
        except ImportError:
            from model_registry import auto_configure

        model_path = os.getenv("LLM_MODEL_PATH", cls.model_path)

        # Auto-detect optimal params; explicit env-vars override.
        override_ctx = int(os.getenv("LLM_CTX_SIZE")) if os.getenv("LLM_CTX_SIZE") else None
        auto = auto_configure(model_path, override_ctx=override_ctx)

        device = os.getenv("LLM_DEVICE", cls.device).strip().lower()

        return cls(
            model_path=model_path,
            engine=os.getenv("LLM_ENGINE", cls.engine).strip().lower(),
            device=device,
            n_gpu_layers=resolve_gpu_layers(device, os.getenv("LLM_GPU_LAYERS")),
            tier=os.getenv("LLM_TIER", cls.tier).strip(),
            flash_attn=_env_bool("LLM_FLASH_ATTN", cls.flash_attn),
            kv_cache_type=os.getenv("LLM_KV_CACHE_TYPE", cls.kv_cache_type).strip().lower(),
            n_ubatch=int(os.getenv("LLM_N_UBATCH", str(cls.n_ubatch))),
            mlock=_env_bool("LLM_MLOCK", cls.mlock),
            n_ctx=auto["n_ctx"],
            n_threads=int(os.getenv("LLM_THREADS", str(cls.n_threads))),
            n_batch=int(os.getenv("LLM_N_BATCH") or os.getenv("LLM_BATCH_SIZE") or str(cls.n_batch)),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", str(auto["max_tokens"]))),
            default_temperature=float(os.getenv("LLM_TEMPERATURE", str(auto["default_temperature"]))),
            host=os.getenv("LLM_HOST", cls.host),
            port=int(os.getenv("LLM_PORT", str(cls.port))),
            max_workers=int(os.getenv("LLM_MAX_WORKERS", str(cls.max_workers))),
            verbose=bool(int(os.getenv("LLM_VERBOSE", "0"))),
        )
    
    def validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If model file doesn't exist
        """
        if self.engine not in VALID_ENGINES:
            raise ValueError(f"LLM_ENGINE must be one of {VALID_ENGINES}, got {self.engine!r}")
        if self.device not in VALID_DEVICES:
            raise ValueError(f"LLM_DEVICE must be one of {VALID_DEVICES}, got {self.device!r}")
        if self.kv_cache_type not in VALID_KV_TYPES:
            raise ValueError(
                f"LLM_KV_CACHE_TYPE must be one of {VALID_KV_TYPES}, got {self.kv_cache_type!r}"
            )
        if self.kv_cache_type != "f16" and not self.flash_attn:
            raise ValueError("A quantized KV cache requires LLM_FLASH_ATTN=1")
        if self.engine == "mlx" and self.model_path.endswith(".gguf"):
            raise ValueError("The mlx engine cannot load a .gguf file; use an MLX model id or directory")

        # Validate model exists (a Hugging Face repo id is resolved by the engine)
        if is_local_model_path(self.model_path) and not Path(self.model_path).exists():
            raise FileNotFoundError(f"Model file not found: {self.model_path}")
        
        # Validate numeric ranges
        if self.n_ctx < 512:
            raise ValueError(f"n_ctx must be >= 512, got {self.n_ctx}")
        
        if self.n_threads < 1:
            raise ValueError(f"n_threads must be >= 1, got {self.n_threads}")
        
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}")
        
        if not 0.0 <= self.default_temperature <= 2.0:
            raise ValueError(
                f"default_temperature must be in [0.0, 2.0], got {self.default_temperature}"
            )
        
        if self.port < 1024 or self.port > 65535:
            raise ValueError(f"port must be in [1024, 65535], got {self.port}")
        
        logger.info("Configuration validated successfully")
    
    def log_config(self) -> None:
        """Log configuration for debugging."""
        logger.info("LLM Service Configuration:")
        logger.info(f"  Model: {Path(self.model_path).name}")
        logger.info(f"  Engine: {self.engine}  Device: {self.device}  GPU layers: {self.n_gpu_layers}")
        logger.info(f"  Tier: {self.tier or '(registry)'}  Flash attn: {self.flash_attn}  "
                    f"KV cache: {self.kv_cache_type}  uBatch: {self.n_ubatch}  mlock: {self.mlock}")
        logger.info(f"  Context: {self.n_ctx} tokens")
        logger.info(f"  Threads: {self.n_threads}")
        logger.info(f"  Batch: {self.n_batch}")
        logger.info(f"  Max Tokens: {self.max_tokens}")
        logger.info(f"  Temperature: {self.default_temperature}")
        logger.info(f"  Server: {self.host}:{self.port}")
        logger.info(f"  Workers: {self.max_workers}")


def get_config() -> LLMServiceConfig:
    """
    Get LLM service configuration.
    
    Loads from environment variables, validates, and returns config instance.
    
    Returns:
        LLMServiceConfig: Validated configuration
    
    Example:
        >>> config = get_config()
        >>> config.validate()
        >>> config.log_config()
    """
    config = LLMServiceConfig.from_env()
    config.validate()
    return config
