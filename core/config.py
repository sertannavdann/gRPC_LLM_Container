"""
Configuration management for agent workflows.

Provides centralized loading and validation of configuration from
environment variables, .env files, and config files.
"""

import os
import logging
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from .state import WorkflowConfig, ModelConfig

logger = logging.getLogger(__name__)


class ConfigLoader:
    """
    Load and validate agent configuration from multiple sources.
    
    Priority (highest to lowest):
    1. Environment variables
    2. .env file
    3. Default values
    
    Example:
        >>> loader = ConfigLoader()
        >>> workflow_config = loader.load_workflow_config()
        >>> model_config = loader.load_model_config()
    """
    
    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize config loader.
        
        Args:
            env_file: Path to .env file (default: .env in working directory)
        """
        if env_file:
            load_dotenv(env_file)
        else:
            # Try to load .env from current directory
            env_path = Path.cwd() / ".env"
            if env_path.exists():
                load_dotenv(env_path)
                logger.info(f"Loaded configuration from {env_path}")
        
        self._loaded_from_env = bool(env_file or env_path.exists())
    
    def load_workflow_config(self) -> WorkflowConfig:
        """
        Load workflow configuration from environment.
        
        Environment variables:
        - AGENT_MAX_ITERATIONS: Maximum tool->LLM cycles (default: 5)
        - AGENT_CONTEXT_WINDOW: Number of recent messages (default: 3)
        - AGENT_TEMPERATURE: LLM temperature 0.0-2.0 (default: 0.7)
        - AGENT_MODEL_NAME: GGUF model filename
        - AGENT_ENABLE_STREAMING: Enable streaming (default: true)
        - AGENT_MAX_TOOL_CALLS: Max parallel tools (default: 5)
        - AGENT_TIMEOUT: Workflow timeout seconds (default: 120)
        
        Returns:
            WorkflowConfig: Validated configuration instance
        """
        config = WorkflowConfig(
            max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "5")),
            context_window=int(os.getenv("AGENT_CONTEXT_WINDOW", "3")),
            temperature=float(os.getenv("AGENT_TEMPERATURE", "0.7")),
            model_name=os.getenv("AGENT_MODEL_NAME", "qwen2.5-0.5b-instruct-q5_k_m.gguf"),
            enable_streaming=os.getenv("AGENT_ENABLE_STREAMING", "true").lower() == "true",
            max_tool_calls_per_turn=int(os.getenv("AGENT_MAX_TOOL_CALLS", "5")),
            timeout_seconds=int(os.getenv("AGENT_TIMEOUT", "120")),
        )
        
        logger.info(
            f"Loaded WorkflowConfig: max_iterations={config.max_iterations}, "
            f"temperature={config.temperature}, model={config.model_name}"
        )
        
        return config
    
    def load_model_config(self) -> ModelConfig:
        """
        Load local LLM configuration from environment.
        
        Environment variables:
        - LLM_MODEL_PATH: Absolute path to GGUF file
        - LLM_N_CTX: Context window size (default: 2048)
        - LLM_N_THREADS: CPU threads (default: 4)
        - LLM_N_GPU_LAYERS: Metal GPU layers (default: 0)
        - LLM_USE_MLOCK: Lock model in RAM (default: false)
        - LLM_USE_MMAP: Memory-map model (default: true)
        
        Returns:
            ModelConfig: Validated model configuration
        """
        config = ModelConfig(
            model_path=os.getenv("LLM_MODEL_PATH", "inference/models/qwen2.5-3b-instruct-q5_k_m.gguf"),
            n_ctx=int(os.getenv("LLM_N_CTX", "2048")),
            n_threads=int(os.getenv("LLM_N_THREADS", "4")),
            n_gpu_layers=int(os.getenv("LLM_N_GPU_LAYERS", "0")),
            use_mlock=os.getenv("LLM_USE_MLOCK", "false").lower() == "true",
            use_mmap=os.getenv("LLM_USE_MMAP", "true").lower() == "true",
        )
        
        logger.info(
            f"Loaded ModelConfig: n_ctx={config.n_ctx}, "
            f"n_threads={config.n_threads}, n_gpu_layers={config.n_gpu_layers}"
        )
        
        return config
    
    def get_api_keys(self) -> dict[str, Optional[str]]:
        """
        Extract API keys from environment.
        
        Returns:
            dict: Available API keys (None if not set)
        """
        keys = {
            "serper_api_key": os.getenv("SERPER_API_KEY"),
            "google_maps_api_key": os.getenv("GOOGLE_MAPS_API_KEY"),
        }
        
        available = {k: v for k, v in keys.items() if v}
        logger.info(f"Loaded {len(available)} API keys")
        
        return keys


def load_config(env_file: Optional[str] = None) -> tuple[WorkflowConfig, ModelConfig]:
    """
    Convenience function to load all configuration.
    
    Args:
        env_file: Optional path to .env file
    
    Returns:
        tuple: (WorkflowConfig, ModelConfig)
    
    Example:
        >>> workflow_config, model_config = load_config(".env.production")
        >>> workflow = AgentWorkflow(registry, llm_engine, workflow_config)
    """
    loader = ConfigLoader(env_file)
    workflow_config = loader.load_workflow_config()
    model_config = loader.load_model_config()
    
    return workflow_config, model_config
