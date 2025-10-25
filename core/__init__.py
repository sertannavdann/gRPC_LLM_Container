"""
Core agent framework components following Google ADK and LangGraph patterns.

This module provides the foundational building blocks for local LLM agents:
- State management with TypedDict and Annotated reducers
- LangGraph workflow construction
- SQLite checkpointing for conversation memory
- Configuration management

Example:
    >>> from core import AgentState, AgentWorkflow, WorkflowConfig
    >>> config = WorkflowConfig(max_iterations=5, temperature=0.7)
    >>> workflow = AgentWorkflow(tool_registry, llm_engine, config)
    >>> result = workflow.run("Hello, world!")
"""

from .state import AgentState, WorkflowConfig, ModelConfig
from .graph import AgentWorkflow
from .checkpointing import CheckpointManager
from .config import load_config, ConfigLoader

__all__ = [
    "AgentState",
    "WorkflowConfig",
    "ModelConfig",
    "AgentWorkflow",
    "CheckpointManager",
    "load_config",
    "ConfigLoader",
]

__version__ = "1.0.0"
