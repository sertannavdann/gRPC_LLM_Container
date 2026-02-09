"""
Agent state management following LangGraph patterns.

Provides type-safe state containers with automatic message merging and
validation. All state modifications flow through Annotated reducers for
predictable graph behavior.
"""

from typing import TypedDict, Annotated, Sequence, Literal, Optional
from datetime import datetime
from langchain_core.messages import BaseMessage
from langgraph.graph import add_messages
from pydantic import BaseModel, Field


class AgentState(TypedDict):
    """
    Agent workflow state with message history and execution tracking.
    
    Follows LangGraph's recommended state structure with Annotated reducers
    for automatic message merging and deduplication.
    
    Attributes:
        messages: Conversation history with automatic merge on update
        tool_results: List of tool execution results with metadata
        router_recommendation: Router's service recommendation (for observability)
        next_action: Routing decision for next graph node
        error: Error message if workflow fails
        retry_count: Number of retry attempts for current operation
        conversation_id: Unique identifier for conversation thread
        user_id: Optional user identifier for multi-tenant systems
        metadata: Additional context (e.g., session info, permissions)
    """
    
    # Message history with automatic merge reducer
    messages: Annotated[Sequence[BaseMessage], add_messages]
    
    # Tool execution tracking
    tool_results: list[dict]  # [{tool_name, result, timestamp, latency_ms}]
    
    # Router recommendation (for observability and checkpointing)
    router_recommendation: Optional[dict]  # Router's service recommendations
    
    # Routing control for graph execution
    next_action: Optional[Literal["llm", "tools", "validate", "end"]]
    
    # Error handling
    error: Optional[str]
    retry_count: int
    
    # Context management
    conversation_id: str
    user_id: Optional[str]
    metadata: dict


class WorkflowConfig(BaseModel):
    """
    Immutable workflow configuration for agent behavior.
    
    Controls iteration limits, context windows, and LLM parameters.
    All settings are validated at initialization.
    
    Attributes:
        max_iterations: Maximum tool->LLM cycles before forcing termination
        context_window: Number of recent messages to include in LLM context
        temperature: LLM sampling temperature (0.0=deterministic, 1.0=creative)
        model_name: Local GGUF model filename
        enable_streaming: Whether to stream LLM responses token-by-token
        max_tool_calls_per_turn: Limit parallel tool calls to prevent runaway
        timeout_seconds: Global timeout for workflow execution
    """
    
    max_iterations: int = Field(default=5, ge=1, le=20)
    context_window: int = Field(default=12, ge=1, le=50)
    temperature: float = Field(default=0.15, ge=0.0, le=2.0)
    model_name: str = Field(default="Mistral-Small-24B-Instruct-2501.Q8_0.gguf")
    enable_streaming: bool = Field(default=True)
    max_tool_calls_per_turn: int = Field(default=5, ge=1, le=10)
    timeout_seconds: int = Field(default=120, ge=10, le=600)
    
    class Config:
        frozen = True  # Immutable after creation


class ModelConfig(BaseModel):
    """
    Local LLM inference configuration for llama.cpp.
    
    Optimized for Apple Silicon with Metal acceleration. Adjust
    n_threads and n_gpu_layers based on your hardware.
    
    Attributes:
        model_path: Absolute path to GGUF model file
        n_ctx: Context window size (must match model's training)
        n_threads: CPU threads for inference (set to physical cores)
        n_gpu_layers: Number of layers to offload to Metal GPU
        use_mlock: Lock model in RAM to prevent swapping
        use_mmap: Memory-map model file for faster loading
        logits_all: Compute logits for all tokens (needed for perplexity)
        vocab_only: Load only vocabulary (for tokenization tasks)
    """
    
    model_path: str = Field(
        default="inference/models/Mistral-Small-24B-Instruct-2501.Q8_0.gguf"
    )
    n_ctx: int = Field(default=16384, ge=512, le=131072)
    n_threads: int = Field(default=4, ge=1, le=16)
    n_gpu_layers: int = Field(default=0, ge=0, le=100)  # Metal acceleration
    use_mlock: bool = Field(default=False)  # Set True for production
    use_mmap: bool = Field(default=True)  # Fast loading
    logits_all: bool = Field(default=False)
    vocab_only: bool = Field(default=False)
    
    class Config:
        frozen = True


class ToolExecutionResult(BaseModel):
    """
    Standardized tool execution result for state tracking.
    
    Captures all metadata needed for observability, debugging,
    and prompt construction.
    
    Attributes:
        tool_name: Name of executed tool
        status: Execution status (success/error/timeout)
        result: Tool return value (always dict with "status" key)
        timestamp: ISO 8601 execution start time
        latency_ms: Execution duration in milliseconds
        error_message: Optional error details if status=error
        retry_count: Number of retry attempts for this call
    """
    
    tool_name: str
    status: Literal["success", "error", "timeout"]
    result: dict
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())
    latency_ms: float
    error_message: Optional[str] = None
    retry_count: int = 0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for AgentState.tool_results"""
        return self.model_dump()


def create_initial_state(
    conversation_id: str,
    user_id: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> AgentState:
    """
    Factory function for creating initial agent state.
    
    Args:
        conversation_id: Unique conversation identifier (UUID recommended)
        user_id: Optional user identifier for multi-tenant deployments
        metadata: Additional context (e.g., {"source": "web", "locale": "en-US"})
    
    Returns:
        AgentState: Initialized state ready for workflow execution
    
    Example:
        >>> state = create_initial_state("conv-123", user_id="user-456")
        >>> workflow.run(state, input_message="Hello!")
    """
    return AgentState(
        messages=[],
        tool_results=[],
        router_recommendation=None,
        next_action=None,
        error=None,
        retry_count=0,
        conversation_id=conversation_id,
        user_id=user_id,
        metadata=metadata or {},
    )
