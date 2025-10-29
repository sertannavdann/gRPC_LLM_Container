"""
Configuration for Agent Service.

Centralizes all agent service settings including router config, adapter config,
checkpoint paths, and service configuration. Supports environment variable overrides.
"""

import os
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RouterConfig:
    """
    Configuration for the embedded router.
    
    Attributes:
        model_path: Path to router model (Qwen2.5-3B)
        max_tokens: Maximum tokens for router output
        temperature: Sampling temperature
        n_ctx: Context window size
        n_threads: CPU threads for inference
        timeout_seconds: Router timeout
        enabled: Whether router is enabled
    """
    model_path: str = "/app/models/qwen2.5-3b-instruct-q5_k_m.gguf"
    max_tokens: int = 256
    temperature: float = 0.1
    n_ctx: int = 4096
    n_threads: int = 4
    timeout_seconds: int = 10
    enabled: bool = True
    
    @classmethod
    def from_env(cls) -> "RouterConfig":
        """
        Load router configuration from environment variables.
        
        Environment variables:
            ROUTER_MODEL_PATH: Path to router model
            ROUTER_MAX_TOKENS: Max tokens
            ROUTER_TEMPERATURE: Temperature
            ROUTER_CTX_SIZE: Context size
            ROUTER_THREADS: CPU threads
            ROUTER_TIMEOUT: Timeout seconds
            ROUTER_ENABLED: Enable router (1/0)
        
        Returns:
            RouterConfig: Configuration instance
        """
        return cls(
            model_path=os.getenv("ROUTER_MODEL_PATH", cls.model_path),
            max_tokens=int(os.getenv("ROUTER_MAX_TOKENS", str(cls.max_tokens))),
            temperature=float(os.getenv("ROUTER_TEMPERATURE", str(cls.temperature))),
            n_ctx=int(os.getenv("ROUTER_CTX_SIZE", str(cls.n_ctx))),
            n_threads=int(os.getenv("ROUTER_THREADS", str(cls.n_threads))),
            timeout_seconds=int(os.getenv("ROUTER_TIMEOUT", str(cls.timeout_seconds))),
            enabled=bool(int(os.getenv("ROUTER_ENABLED", "1"))),
        )
    
    def validate(self) -> None:
        """
        Validate router configuration.
        
        Raises:
            ValueError: If configuration is invalid
            FileNotFoundError: If model file doesn't exist (when enabled)
        """
        if not self.enabled:
            logger.info("Router is disabled, skipping validation")
            return
        
        # Validate model exists
        model_path = Path(self.model_path)
        if not model_path.exists():
            raise FileNotFoundError(f"Router model not found: {self.model_path}")
        
        # Validate numeric ranges
        if self.max_tokens < 1:
            raise ValueError(f"max_tokens must be >= 1, got {self.max_tokens}")
        
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be in [0.0, 2.0], got {self.temperature}"
            )
        
        if self.timeout_seconds < 1:
            raise ValueError(
                f"timeout_seconds must be >= 1, got {self.timeout_seconds}"
            )
        
        logger.info("Router configuration validated successfully")


@dataclass
class AgentServiceConfig:
    """
    Configuration for Agent Service.
    
    Attributes:
        checkpoint_db_path: Path to SQLite checkpoint database
        max_iterations: Maximum workflow iterations
        temperature: Default LLM temperature
        context_window: Conversation context window
        enable_streaming: Enable streaming responses
        timeout_seconds: Query timeout
        system_prompt: Optional custom system prompt
        host: gRPC server host
        port: gRPC server port
        max_workers: ThreadPoolExecutor workers
        router_config: Router configuration
    """
    # Checkpoint configuration
    checkpoint_db_path: str = "./data/agent_checkpoints.db"
    
    # Workflow configuration
    max_iterations: int = 5
    temperature: float = 0.7
    context_window: int = 3
    enable_streaming: bool = False
    timeout_seconds: int = 30
    system_prompt: Optional[str] = None
    
    # Service configuration
    host: str = "[::]"
    port: int = 50054
    max_workers: int = 10
    
    # Router configuration (nested)
    router_config: Optional[RouterConfig] = None
    
    @classmethod
    def from_env(cls) -> "AgentServiceConfig":
        """
        Load configuration from environment variables.
        
        Environment variables:
            AGENT_CHECKPOINT_DB: Checkpoint database path
            AGENT_MAX_ITERATIONS: Max workflow iterations
            AGENT_TEMPERATURE: LLM temperature
            AGENT_CONTEXT_WINDOW: Context window size
            AGENT_ENABLE_STREAMING: Enable streaming (1/0)
            AGENT_TIMEOUT: Timeout seconds
            AGENT_SYSTEM_PROMPT: Custom system prompt
            AGENT_HOST: gRPC host
            AGENT_PORT: gRPC port
            AGENT_MAX_WORKERS: Max workers
        
        Returns:
            AgentServiceConfig: Configuration instance
        """
        return cls(
            checkpoint_db_path=os.getenv("AGENT_CHECKPOINT_DB", cls.checkpoint_db_path),
            max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", str(cls.max_iterations))),
            temperature=float(os.getenv("AGENT_TEMPERATURE", str(cls.temperature))),
            context_window=int(os.getenv("AGENT_CONTEXT_WINDOW", str(cls.context_window))),
            enable_streaming=bool(int(os.getenv("AGENT_ENABLE_STREAMING", "0"))),
            timeout_seconds=int(os.getenv("AGENT_TIMEOUT", str(cls.timeout_seconds))),
            system_prompt=os.getenv("AGENT_SYSTEM_PROMPT"),
            host=os.getenv("AGENT_HOST", cls.host),
            port=int(os.getenv("AGENT_PORT", str(cls.port))),
            max_workers=int(os.getenv("AGENT_MAX_WORKERS", str(cls.max_workers))),
            router_config=RouterConfig.from_env(),
        )
    
    def validate(self) -> None:
        """
        Validate configuration values.
        
        Raises:
            ValueError: If configuration is invalid
        """
        # Validate numeric ranges
        if self.max_iterations < 1:
            raise ValueError(f"max_iterations must be >= 1, got {self.max_iterations}")
        
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError(
                f"temperature must be in [0.0, 2.0], got {self.temperature}"
            )
        
        if self.context_window < 1:
            raise ValueError(
                f"context_window must be >= 1, got {self.context_window}"
            )
        
        if self.timeout_seconds < 1:
            raise ValueError(
                f"timeout_seconds must be >= 1, got {self.timeout_seconds}"
            )
        
        if self.port < 1024 or self.port > 65535:
            raise ValueError(f"port must be in [1024, 65535], got {self.port}")
        
        # Validate checkpoint path parent exists
        checkpoint_path = Path(self.checkpoint_db_path)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Validate router config if present
        if self.router_config:
            self.router_config.validate()
        
        logger.info("Agent service configuration validated successfully")
    
    def log_config(self) -> None:
        """Log configuration for debugging."""
        logger.info("Agent Service Configuration:")
        logger.info(f"  Checkpoint DB: {self.checkpoint_db_path}")
        logger.info(f"  Max Iterations: {self.max_iterations}")
        logger.info(f"  Temperature: {self.temperature}")
        logger.info(f"  Context Window: {self.context_window}")
        logger.info(f"  Streaming: {self.enable_streaming}")
        logger.info(f"  Timeout: {self.timeout_seconds}s")
        logger.info(f"  Server: {self.host}:{self.port}")
        logger.info(f"  Workers: {self.max_workers}")
        if self.router_config:
            logger.info(f"  Router: {'enabled' if self.router_config.enabled else 'disabled'}")
            if self.router_config.enabled:
                logger.info(f"    Model: {Path(self.router_config.model_path).name}")
                logger.info(f"    Timeout: {self.router_config.timeout_seconds}s")


def get_config() -> AgentServiceConfig:
    """
    Get agent service configuration.
    
    Loads from environment variables, validates, and returns config instance.
    
    Returns:
        AgentServiceConfig: Validated configuration
    
    Example:
        >>> config = get_config()
        >>> config.validate()
        >>> config.log_config()
    """
    config = AgentServiceConfig.from_env()
    config.validate()
    return config
