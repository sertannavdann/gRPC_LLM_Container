"""
Orchestrator service configuration.

Consolidates configuration from agent_service and llm_service into a single
unified config for the orchestrator.
"""

import os
from typing import Optional
from dataclasses import dataclass


@dataclass
class OrchestratorConfig:
    """
    Configuration for orchestrator service.
    
    Combines agent workflow settings and LLM service settings.
    """
    # Service settings
    host: str = "0.0.0.0"
    port: int = 50054
    
    # LLM service connection
    llm_host: str = "llm_service"
    llm_port: int = 50051
    
    # Chroma service connection  
    chroma_host: str = "chroma_service"
    chroma_port: int = 50052
    
    # Workflow settings
    max_iterations: int = 5
    context_window: int = 3
    temperature: float = 0.7
    model_name: str = "qwen2.5-0.5b-instruct-q5_k_m.gguf"
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
    
    @classmethod
    def from_env(cls) -> "OrchestratorConfig":
        """Load configuration from environment variables."""
        return cls(
            host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("ORCHESTRATOR_PORT", "50054")),
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
        )
