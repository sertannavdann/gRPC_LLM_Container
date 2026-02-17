"""
Orchestrator service configuration.

Unified config for the orchestrator including LLM provider settings,
tool configuration, and service endpoints.

Supports multiple LLM providers:
- local: Uses local llama.cpp via gRPC (default)
- perplexity: Uses Perplexity Sonar API
- openai: Uses OpenAI API
- nvidia: Uses NVIDIA NIM OpenAI-compatible API
- anthropic: Uses Anthropic Claude API
- openclaw: Uses OpenClaw Gateway (gpt-5.x via Copilot proxy)
"""

import os
from typing import Optional, Dict, Any
from dataclasses import dataclass, field


@dataclass
class OrchestratorConfig:
    """
    Configuration for orchestrator service.
    
    Combines agent workflow settings and LLM service settings.
    """
    # Service settings
    host: str = "0.0.0.0"
    port: int = 50054
    
    # LLM Provider settings (NEW)
    provider_type: str = "local"  # local, perplexity, openai, nvidia, anthropic, openclaw
    provider_api_key: Optional[str] = None
    provider_base_url: Optional[str] = None
    provider_model: Optional[str] = None  # Model name for online providers
    provider_timeout: int = 60
    provider_top_p: Optional[float] = None
    provider_thinking: Optional[bool] = None  # None=provider default, True=thinking, False=instant
    provider_max_tokens: Optional[int] = None
    
    # LLM service connection (for local provider)
    llm_host: str = "llm_service"
    llm_port: int = 50051
    
    # Chroma service connection  
    chroma_host: str = "chroma_service"
    chroma_port: int = 50052
    
    # Workflow settings
    max_iterations: int = 5
    context_window: int = 12
    temperature: float = 0.15
    model_name: str = "qwen2.5-3b-instruct-q5_k_m.gguf"
    enable_streaming: bool = True
    max_tool_calls_per_turn: int = 5
    timeout_seconds: int = 120
    
    # Checkpoint settings
    checkpoint_db_path: str = "agent_memory.sqlite"
    
    # Sandbox service connection
    sandbox_host: str = "sandbox_service"
    sandbox_port: int = 50057
    
    # Self-consistency settings (Agent0 Phase 2)
    enable_self_consistency: bool = False
    self_consistency_samples: int = 5
    self_consistency_threshold: float = 0.6

    # LIDM: Delegation settings
    enable_delegation: bool = False
    llm_heavy_host: str = "llm_service:50051"
    llm_standard_host: str = "llm_service_standard:50051"
    llm_ultra_host: str = ""
    
    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        """Load configuration from environment variables."""
        # Determine provider type
        provider_type = os.getenv("LLM_PROVIDER", "local")
        
        # Get API key based on provider type
        api_key = None
        base_url = None
        if provider_type == "perplexity":
            api_key = os.getenv("PERPLEXITY_API_KEY")
        elif provider_type == "openai":
            api_key = os.getenv("OPENAI_API_KEY")
        elif provider_type == "nvidia":
            api_key = os.getenv("NIM_API_KEY")
            base_url = os.getenv("NIM_BASE_URL", "https://integrate.api.nvidia.com/v1")
        elif provider_type == "anthropic":
            api_key = os.getenv("ANTHROPIC_API_KEY")
        elif provider_type == "openclaw":
            # OpenClaw uses token auth, API key is optional
            api_key = os.getenv("OPENCLAW_API_KEY", "openclaw")
            # Default to host.docker.internal for Docker-to-host communication
            base_url = os.getenv("OPENCLAW_URL", "http://host.docker.internal:18789/v1")
        
        # Allow override via generic base URL env var
        base_url = os.getenv("LLM_PROVIDER_BASE_URL", base_url)

        provider_top_p_env = os.getenv("LLM_PROVIDER_TOP_P")
        if provider_top_p_env is None or provider_top_p_env.strip() == "":
            provider_top_p = 0.95 if provider_type == "nvidia" else 1.0
        else:
            provider_top_p = float(provider_top_p_env)

        thinking_env = os.getenv("LLM_PROVIDER_THINKING")
        provider_thinking = None
        if thinking_env is not None and thinking_env.strip() != "":
            provider_thinking = thinking_env.strip().lower() in {"1", "true", "yes", "on"}

        provider_max_tokens_env = os.getenv("LLM_PROVIDER_MAX_TOKENS")
        provider_max_tokens = int(provider_max_tokens_env) if provider_max_tokens_env else (16384 if provider_type == "nvidia" else None)
        
        # Get model based on provider type
        provider_model = os.getenv("LLM_PROVIDER_MODEL")
        if not provider_model:
            # Set reasonable defaults per provider
            if provider_type == "perplexity":
                provider_model = "sonar-pro"
            elif provider_type == "openai":
                provider_model = "gpt-4o-mini"
            elif provider_type == "nvidia":
                provider_model = "moonshotai/kimi-k2.5"
            elif provider_type == "anthropic":
                provider_model = "claude-3-5-sonnet-20241022"
            elif provider_type == "openclaw":
                provider_model = "gpt-5.2"
        
        return cls(
            host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("ORCHESTRATOR_PORT", "50054")),
            # Provider settings
            provider_type=provider_type,
            provider_api_key=api_key,
            provider_base_url=base_url,
            provider_model=provider_model,
            provider_timeout=int(os.getenv("LLM_PROVIDER_TIMEOUT", "60")),
            provider_top_p=provider_top_p,
            provider_thinking=provider_thinking,
            provider_max_tokens=provider_max_tokens,
            # Local LLM settings (fallback)
            llm_host=os.getenv("LLM_HOST", "llm_service"),
            llm_port=int(os.getenv("LLM_PORT", "50051")),
            chroma_host=os.getenv("CHROMA_HOST", "chroma_service"),
            chroma_port=int(os.getenv("CHROMA_PORT", "50052")),
            max_iterations=int(os.getenv("AGENT_MAX_ITERATIONS", "5")),
            context_window=int(os.getenv("AGENT_CONTEXT_WINDOW", "3")),
            temperature=float(os.getenv("AGENT_TEMPERATURE", "0.7")),
            model_name=os.getenv("AGENT_MODEL_NAME", "qwen2.5-0.5b-instruct-q5_k_m.gguf"),
            enable_streaming=os.getenv("AGENT_ENABLE_STREAMING", "true").lower() == "true",
            max_tool_calls_per_turn=int(os.getenv("AGENT_MAX_TOOL_CALLS", "5")),
            timeout_seconds=int(os.getenv("AGENT_TIMEOUT", "120")),
            checkpoint_db_path=os.getenv("CHECKPOINT_DB_PATH", "agent_memory.sqlite"),
            sandbox_host=os.getenv("SANDBOX_HOST", "sandbox_service"),
            sandbox_port=int(os.getenv("SANDBOX_PORT", "50057")),
            enable_self_consistency=os.getenv("ENABLE_SELF_CONSISTENCY", "false").lower() == "true",
            self_consistency_samples=int(os.getenv("SELF_CONSISTENCY_SAMPLES", "5")),
            self_consistency_threshold=float(os.getenv("SELF_CONSISTENCY_THRESHOLD", "0.6")),
            # LIDM
            enable_delegation=os.getenv("ENABLE_DELEGATION", "false").lower() == "true",
            llm_heavy_host=os.getenv("LLM_HEAVY_HOST", "llm_service:50051"),
            llm_standard_host=os.getenv("LLM_STANDARD_HOST", "llm_service_standard:50051"),
            llm_ultra_host=os.getenv("LLM_ULTRA_HOST", ""),
        )
