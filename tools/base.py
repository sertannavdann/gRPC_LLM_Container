"""
Base classes and protocols for tool system.

Defines the interface for all tools following Google ADK best practices:
- Tools are callables that return Dict[str, Any]
- All results have a "status" key ("success" or "error")
- Type hints for all parameters
- Structured docstrings with Args and Returns sections
- Idempotency key support for safe retries
"""

from typing import Dict, Any, Protocol, runtime_checkable, Optional, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from functools import wraps
import hashlib
import json
import time
import uuid
import threading
import logging

try:
    from pydantic import BaseModel, ValidationError
except ImportError:
    BaseModel = None  # type: ignore
    ValidationError = None  # type: ignore

logger = logging.getLogger(__name__)

T = TypeVar('T')
TRequest = TypeVar('TRequest')
TResponse = TypeVar('TResponse')


@runtime_checkable
class ToolCallable(Protocol):
    """
    Protocol for tool functions following ADK patterns.
    
    All tools must:
    - Accept kwargs with type hints
    - Return Dict[str, Any] with "status" key
    - Have docstring with Args/Returns sections
    """
    
    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        """Execute tool with provided arguments."""
        ...


@dataclass
class ToolResult:
    """
    Standardized tool result format following ADK patterns.
    
    All tools should return dictionaries, but this class provides
    a convenient way to construct standardized results.
    
    Attributes:
        status: "success" or "error"
        data: Tool-specific return data (optional)
        message: Human-readable message (optional)
    
    Example:
        >>> result = ToolResult(status="success", data={"count": 5})
        >>> return result.to_dict()
    """
    
    status: str  # "success" | "error"
    data: Any = None
    message: str = ""
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to dictionary format expected by LLMs.

        Returns:
            dict: Standardized result with status key
        """
        result = {"status": self.status}
        if self.data is not None:
            result["data"] = self.data
        if self.message:
            result["message"] = self.message
        if self.error is not None:
            result["error"] = self.error
        if self.metadata:
            result["_metadata"] = self.metadata
        return result


class ToolError(Exception):
    """
    Tool execution error with standardized formatting.
    
    Provides automatic conversion to error dictionary format
    for consistent error handling across the agent system.
    
    Attributes:
        message: Error description
        tool_name: Name of tool that failed (optional)
    
    Example:
        >>> raise ToolError("API request failed", tool_name="web_search")
    """
    
    def __init__(self, message: str, tool_name: Optional[str] = None):
        self.message = message
        self.tool_name = tool_name
        super().__init__(message)
    
    def to_dict(self) -> Dict[str, Any]:
        """
        Convert to error dictionary.
        
        Returns:
            dict: Error result with status="error"
        """
        result = {
            "status": "error",
            "error": self.message
        }
        if self.tool_name:
            result["tool"] = self.tool_name
        return result


class BaseToolLegacy:
    """
    Legacy base class for tools requiring stateful initialization.

    Renamed from BaseTool for backward compatibility. New tools should
    inherit from the new BaseTool ABC instead.

    Most tools should be simple functions decorated with @tool.
    Use this class only when you need:
    - API clients with authentication
    - Connection pooling
    - Shared configuration across calls

    Example:
        >>> class WebSearchTool(BaseToolLegacy):
        ...     def __init__(self, api_key: str):
        ...         self.api_key = api_key
        ...
        ...     def execute(self, query: str) -> Dict[str, Any]:
        ...         # Use self.api_key for API calls
        ...         return {"status": "success", "results": [...]}
    """

    name: str = ""
    description: str = ""

    def execute(self, **kwargs: Any) -> Dict[str, Any]:
        """
        Execute tool with provided arguments.

        Must be overridden by subclasses.

        Args:
            **kwargs: Tool-specific arguments

        Returns:
            dict: Result with "status" key

        Raises:
            NotImplementedError: If not overridden by subclass
        """
        raise NotImplementedError(f"{self.__class__.__name__}.execute() not implemented")

    def __call__(self, **kwargs: Any) -> Dict[str, Any]:
        """Make tool instances callable."""
        return self.execute(**kwargs)


# =============================================================================
# NEW TOOL ABSTRACTIONS (Phase 05-05)
# =============================================================================


class BaseTool(ABC, Generic[TRequest, TResponse]):
    """
    Abstract base class for all tools with typed request/response lifecycle.

    Mirrors the BaseAdapter[T] pattern from shared/adapters/base.py.
    Subclasses implement validate_input, execute_internal, and format_output.

    The execute() method orchestrates the full lifecycle:
    validate_input -> execute_internal -> format_output, with timing and error handling.

    Type Parameters:
        TRequest: The validated request type (typically a Pydantic BaseModel)
        TResponse: The response type from execute_internal

    Example:
        >>> class MyTool(BaseTool[MyRequest, MyResponse]):
        ...     name = "my_tool"
        ...     description = "Does something useful"
        ...
        ...     def validate_input(self, **kwargs) -> MyRequest:
        ...         return MyRequest(**kwargs)
        ...
        ...     def execute_internal(self, request: MyRequest) -> MyResponse:
        ...         return MyResponse(result="done")
        ...
        ...     def format_output(self, response: MyResponse) -> Dict[str, Any]:
        ...         return {"result": response.result}
    """

    name: str = ""
    description: str = ""
    version: str = "1.0.0"

    @abstractmethod
    def validate_input(self, **kwargs) -> TRequest:
        """
        Validate and parse raw kwargs into a typed request object.

        Args:
            **kwargs: Raw arguments from the caller

        Returns:
            TRequest: Validated request object

        Raises:
            ValueError: If validation fails
        """
        ...

    @abstractmethod
    def execute_internal(self, request: TRequest) -> TResponse:
        """
        Execute the core tool logic with a validated request.

        Args:
            request: Validated request object from validate_input

        Returns:
            TResponse: Raw response from tool execution
        """
        ...

    @abstractmethod
    def format_output(self, response: TResponse) -> Dict[str, Any]:
        """
        Format the raw response into a dictionary for LLM consumption.

        Args:
            response: Raw response from execute_internal

        Returns:
            dict: Formatted output data
        """
        ...

    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Orchestrate the full tool lifecycle: validate -> execute -> format.

        Handles timing, request ID generation, and error handling.
        Returns a dict with 'status' key and '_metadata' dict.

        Args:
            **kwargs: Raw arguments passed to the tool

        Returns:
            dict: Result with status, data, and _metadata keys
        """
        request_id = str(uuid.uuid4())[:8]
        start = time.monotonic()

        try:
            request = self.validate_input(**kwargs)
            response = self.execute_internal(request)
            output = self.format_output(response)

            duration_ms = round((time.monotonic() - start) * 1000, 2)

            result = {
                "status": "success",
                **output,
                "_metadata": {
                    "tool": self.name,
                    "version": self.version,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
            }
            return result

        except (ValueError, TypeError) as e:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.warning(f"Tool {self.name} validation error: {e}")
            return {
                "status": "error",
                "error": str(e),
                "_metadata": {
                    "tool": self.name,
                    "version": self.version,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
            }

        except Exception as e:
            duration_ms = round((time.monotonic() - start) * 1000, 2)
            logger.error(f"Tool {self.name} execution error: {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "_metadata": {
                    "tool": self.name,
                    "version": self.version,
                    "request_id": request_id,
                    "duration_ms": duration_ms,
                },
            }

    def __call__(self, **kwargs) -> Dict[str, Any]:
        """Make tool instances callable, delegating to execute()."""
        return self.execute(**kwargs)

    def get_schema(self) -> Dict[str, Any]:
        """
        Return tool schema for LLM function-calling.

        Returns:
            dict: Schema with name, description, and parameters
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {},
        }


class ActionStrategy(ABC):
    """
    Abstract strategy for a single action within a CompositeTool.

    Each strategy handles one action type (e.g., 'search', 'load', 'build').
    Registered with a CompositeTool via _register_strategy().

    Attributes:
        action_name: Unique name for this action (used for dispatch)
        description: Human-readable description of the action
    """

    action_name: str = ""
    description: str = ""

    @abstractmethod
    def execute(self, **kwargs) -> Dict[str, Any]:
        """
        Execute the action with provided arguments.

        Args:
            **kwargs: Action-specific arguments

        Returns:
            dict: Result data (will be wrapped by CompositeTool)
        """
        ...


class CompositeTool(BaseTool[Dict[str, Any], Dict[str, Any]]):
    """
    Tool that dispatches to registered ActionStrategy instances.

    Uses the Strategy pattern to handle multiple actions within a single tool.
    Subclasses register strategies in __init__ via _register_strategy().

    Example:
        >>> class MyCompositeTool(CompositeTool):
        ...     name = "my_tool"
        ...     description = "Multi-action tool"
        ...
        ...     def __init__(self):
        ...         super().__init__()
        ...         self._register_strategy(SearchStrategy())
        ...         self._register_strategy(LoadStrategy())
    """

    def __init__(self):
        self._strategies: Dict[str, ActionStrategy] = {}

    def _register_strategy(self, strategy: ActionStrategy) -> None:
        """
        Register an action strategy for dispatch.

        Args:
            strategy: ActionStrategy instance with a unique action_name
        """
        self._strategies[strategy.action_name] = strategy

    def validate_input(self, **kwargs) -> Dict[str, Any]:
        """
        Validate that 'action' param exists and maps to a registered strategy.

        Args:
            **kwargs: Must include 'action' key

        Returns:
            dict: The validated kwargs

        Raises:
            ValueError: If action is missing or not registered
        """
        action = kwargs.get("action")
        if not action:
            available = list(self._strategies.keys())
            raise ValueError(
                f"Missing required 'action' parameter. Available actions: {available}"
            )
        if action not in self._strategies:
            available = list(self._strategies.keys())
            raise ValueError(
                f"Unknown action '{action}'. Available actions: {available}"
            )
        return kwargs

    def execute_internal(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """
        Dispatch to the appropriate strategy based on the 'action' key.

        Args:
            request: Validated kwargs containing 'action' key

        Returns:
            dict: Result from the strategy's execute method
        """
        action = request["action"]
        strategy = self._strategies[action]
        # Pass all kwargs except 'action' to the strategy
        strategy_kwargs = {k: v for k, v in request.items() if k != "action"}
        return strategy.execute(**strategy_kwargs)

    def format_output(self, response: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pass through strategy output (strategies return complete dicts).

        Args:
            response: Dict from the strategy

        Returns:
            dict: Same dict, passed through
        """
        return response

    def get_schema(self) -> Dict[str, Any]:
        """
        Return schema including available actions.

        Returns:
            dict: Schema with name, description, parameters, and actions
        """
        actions = {}
        for name, strategy in self._strategies.items():
            actions[name] = {"description": strategy.description}
        return {
            "name": self.name,
            "description": self.description,
            "parameters": {"action": {"type": "string", "enum": list(self._strategies.keys())}},
            "actions": actions,
        }

# =============================================================================
# IDEMPOTENCY SUPPORT
# =============================================================================

def compute_idempotency_key(tool_name: str, args: Dict[str, Any]) -> str:
    """
    Compute a deterministic idempotency key for a tool call.
    
    The key is a hash of the tool name and canonicalized arguments,
    ensuring that identical calls produce identical keys.
    
    Args:
        tool_name: Name of the tool being called
        args: Arguments passed to the tool
        
    Returns:
        SHA-256 hash string (first 16 chars)
        
    Example:
        >>> key = compute_idempotency_key("web_search", {"query": "python"})
        >>> # Returns something like "a1b2c3d4e5f67890"
    """
    # Canonicalize: sort keys, convert to JSON with sorted keys
    canonical = json.dumps(
        {"tool": tool_name, "args": args},
        sort_keys=True,
        separators=(',', ':'),
        default=str  # Handle non-JSON-serializable types
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


@dataclass
class CachedResult:
    """Cached tool result with metadata."""
    result: Dict[str, Any]
    timestamp: float
    tool_name: str


class IdempotencyCache:
    """
    Thread-safe cache for idempotent tool calls.
    
    Prevents duplicate execution of tools by caching results
    based on idempotency keys. Results expire after a TTL.
    
    Attributes:
        ttl_seconds: Time-to-live for cached results (default: 300s)
        max_size: Maximum cache entries (default: 1000)
    
    Example:
        >>> cache = IdempotencyCache(ttl_seconds=300)
        >>> key = compute_idempotency_key("web_search", {"query": "python"})
        >>> 
        >>> # Check cache before executing
        >>> cached = cache.get(key)
        >>> if cached:
        ...     return cached
        >>> 
        >>> # Execute and cache result
        >>> result = tool.execute(**args)
        >>> cache.set(key, result, "web_search")
        >>> return result
    """
    
    def __init__(self, ttl_seconds: float = 300.0, max_size: int = 1000):
        self.ttl_seconds = ttl_seconds
        self.max_size = max_size
        self._cache: Dict[str, CachedResult] = {}
        self._lock = threading.Lock()
    
    def get(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Get cached result if exists and not expired.
        
        Args:
            key: Idempotency key
            
        Returns:
            Cached result dict or None if not found/expired
        """
        with self._lock:
            if key not in self._cache:
                return None
            
            cached = self._cache[key]
            age = time.time() - cached.timestamp
            
            if age > self.ttl_seconds:
                # Expired - remove and return None
                del self._cache[key]
                logger.debug(f"Idempotency cache miss (expired): {key}")
                return None
            
            logger.debug(f"Idempotency cache hit: {key} (age={age:.1f}s)")
            return cached.result
    
    def set(self, key: str, result: Dict[str, Any], tool_name: str) -> None:
        """
        Cache a tool result.
        
        Args:
            key: Idempotency key
            result: Tool result to cache
            tool_name: Name of the tool (for logging)
        """
        with self._lock:
            # Evict oldest entries if at capacity
            if len(self._cache) >= self.max_size:
                self._evict_oldest()
            
            self._cache[key] = CachedResult(
                result=result,
                timestamp=time.time(),
                tool_name=tool_name
            )
            logger.debug(f"Idempotency cache set: {key} for {tool_name}")
    
    def _evict_oldest(self) -> None:
        """Evict oldest 10% of entries."""
        if not self._cache:
            return
        
        # Sort by timestamp and remove oldest 10%
        sorted_keys = sorted(
            self._cache.keys(),
            key=lambda k: self._cache[k].timestamp
        )
        evict_count = max(1, len(sorted_keys) // 10)
        for key in sorted_keys[:evict_count]:
            del self._cache[key]
        logger.debug(f"Evicted {evict_count} entries from idempotency cache")
    
    def clear(self) -> None:
        """Clear all cached results."""
        with self._lock:
            self._cache.clear()
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        with self._lock:
            now = time.time()
            valid = sum(1 for c in self._cache.values() 
                       if now - c.timestamp <= self.ttl_seconds)
            return {
                "total_entries": len(self._cache),
                "valid_entries": valid,
                "ttl_seconds": self.ttl_seconds,
                "max_size": self.max_size,
            }


# Global idempotency cache
_idempotency_cache: Optional[IdempotencyCache] = None


def get_idempotency_cache() -> IdempotencyCache:
    """Get the global idempotency cache."""
    global _idempotency_cache
    if _idempotency_cache is None:
        _idempotency_cache = IdempotencyCache()
    return _idempotency_cache


def idempotent(func: Callable[..., Dict[str, Any]]) -> Callable[..., Dict[str, Any]]:
    """
    Decorator to make a tool function idempotent.
    
    Caches results based on function name and arguments.
    Subsequent calls with identical arguments return cached results.
    
    Example:
        >>> @idempotent
        ... def web_search(query: str) -> Dict[str, Any]:
        ...     # Expensive API call
        ...     return {"status": "success", "results": [...]}
        >>> 
        >>> # First call executes
        >>> result1 = web_search(query="python")
        >>> 
        >>> # Second call returns cached result
        >>> result2 = web_search(query="python")  # No API call
    """
    @wraps(func)
    def wrapper(*args, **kwargs) -> Dict[str, Any]:
        # Build args dict for key computation
        all_args = kwargs.copy()
        # Include positional args if any (by position)
        if args:
            import inspect
            sig = inspect.signature(func)
            params = list(sig.parameters.keys())
            for i, arg in enumerate(args):
                if i < len(params):
                    all_args[params[i]] = arg
        
        tool_name = func.__name__
        key = compute_idempotency_key(tool_name, all_args)
        cache = get_idempotency_cache()
        
        # Check cache
        cached = cache.get(key)
        if cached is not None:
            logger.info(f"Idempotent hit for {tool_name}: returning cached result")
            return cached
        
        # Execute and cache
        result = func(*args, **kwargs)
        cache.set(key, result, tool_name)
        return result
    
    return wrapper