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
    """
    # Model configuration
    model_path: str = "./models/qwen2.5-0.5b-instruct-q5_k_m.gguf"
    n_ctx: int = 4096
    n_threads: int = 4
    n_batch: int = 512
    verbose: bool = False
    
    # Generation defaults
    max_tokens: int = 1024
    default_temperature: float = 0.7
    
    # Service configuration
    host: str = "[::]"
    port: int = 50051
    max_workers: int = 4
    
    @classmethod
    def from_env(cls) -> "LLMServiceConfig":
        """
        Load configuration from environment variables.
        
        Environment variables:
            LLM_MODEL_PATH: Path to GGUF model
            LLM_CTX_SIZE: Context window size
            LLM_THREADS: CPU threads
            LLM_BATCH_SIZE: Batch size
            LLM_MAX_TOKENS: Max generation tokens
            LLM_TEMPERATURE: Default temperature
            LLM_HOST: gRPC host
            LLM_PORT: gRPC port
            LLM_MAX_WORKERS: Max workers
            LLM_VERBOSE: Enable verbose logging (1/0)
        
        Returns:
            LLMServiceConfig: Configuration instance
        """
        return cls(
            model_path=os.getenv("LLM_MODEL_PATH", cls.model_path),
            n_ctx=int(os.getenv("LLM_CTX_SIZE", str(cls.n_ctx))),
            n_threads=int(os.getenv("LLM_THREADS", str(cls.n_threads))),
            n_batch=int(os.getenv("LLM_BATCH_SIZE", str(cls.n_batch))),
            max_tokens=int(os.getenv("LLM_MAX_TOKENS", str(cls.max_tokens))),
            default_temperature=float(os.getenv("LLM_TEMPERATURE", str(cls.default_temperature))),
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
        # Validate model exists
        model_path = Path(self.model_path)
        if not model_path.exists():
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
