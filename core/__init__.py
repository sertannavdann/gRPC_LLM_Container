"""
Core agent framework components following Google ADK and LangGraph patterns.

This module provides the foundational building blocks for local LLM agents:
- State management with TypedDict and Annotated reducers
- LangGraph workflow construction
- SQLite checkpointing for conversation memory and crash recovery

Example:
    >>> from core import AgentState, AgentWorkflow, WorkflowConfig
    >>> config = WorkflowConfig(max_iterations=5, temperature=0.7)
    >>> workflow = AgentWorkflow(tool_registry, llm_engine, config)
    >>> result = workflow.run("Hello, world!")
"""

from .state import AgentState, WorkflowConfig, ModelConfig
from .graph import AgentWorkflow
from .checkpointing import CheckpointManager, RecoveryManager

__all__ = [
    "AgentState",
    "WorkflowConfig",
    "ModelConfig",
    "AgentWorkflow",
    "CheckpointManager",
    "RecoveryManager",
]

__version__ = "1.0.0"
