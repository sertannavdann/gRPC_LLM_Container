"""
Tool decorators for simplified registration following Google ADK patterns.

Provides convenient decorators for registering tools with automatic schema
extraction, circuit breaker integration, and standardized error handling.
"""

import functools
import logging
from typing import Callable, Dict, Any, Optional

from .base import ToolResult, ToolError

logger = logging.getLogger(__name__)


def tool(
    name: Optional[str] = None,
    description: Optional[str] = None,
    max_failures: int = 3
):
    """
    Decorator for registering a function as a tool.
    
    Automatically extracts schema from function signature and docstring.
    Adds circuit breaker protection and standardized error handling.
    
    Args:
        name: Override tool name (default: function name)
        description: Override description (default: from docstring)
        max_failures: Circuit breaker threshold
    
    Example:
        >>> @tool(description="Search the web")
        >>> def web_search(query: str, limit: int = 10) -> dict:
        ...     '''Search using Serper API.
        ...     
        ...     Args:
        ...         query (str): Search query
        ...         limit (int): Max results
        ...     
        ...     Returns:
        ...         Dict with status key
        ...     '''
        ...     return {"status": "success", "results": [...]}
    
    Usage with registry:
        >>> registry = LocalToolRegistry()
        >>> 
        >>> @tool
        >>> def my_tool(param: str) -> dict:
        ...     return {"status": "success"}
        >>> 
        >>> registry.register_function(my_tool)
    """
    def decorator(func: Callable) -> Callable:
        # Store metadata on function
        func._tool_metadata = {
            "name": name or func.__name__,
            "description": description,
            "max_failures": max_failures,
            "is_tool": True
        }
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            try:
                result = func(*args, **kwargs)
                
                # Ensure result has status key
                if isinstance(result, dict):
                    if "status" not in result:
                        result["status"] = "success"
                    return result
                else:
                    # Wrap non-dict results
                    return {"status": "success", "data": result}
                    
            except ToolError as e:
                logger.error(f"Tool error in {func.__name__}: {e}")
                return e.to_dict()
            except Exception as e:
                logger.error(f"Unexpected error in {func.__name__}: {e}", exc_info=True)
                return {
                    "status": "error",
                    "error": str(e),
                    "tool": func.__name__
                }
        
        return wrapper
    
    # Handle both @tool and @tool(...) syntax
    if callable(name):
        # Called as @tool without parentheses
        func = name
        name = None
        return decorator(func)
    else:
        # Called as @tool(...) with arguments
        return decorator


def mcp_tool(
    server_command: str,
    server_args: list[str],
    env: Optional[Dict[str, str]] = None,
    timeout: int = 15
):
    """
    Decorator for wrapping external MCP server tools.
    
    Connects to an MCP server via stdio and exposes its tools
    to the agent system.
    
    Args:
        server_command: Command to run MCP server (e.g., 'npx')
        server_args: Arguments for server command
        env: Environment variables for server
        timeout: Connection timeout in seconds
    
    Example:
        >>> @mcp_tool(
        ...     server_command='npx',
        ...     server_args=["-y", "@modelcontextprotocol/server-google-maps"],
        ...     env={"GOOGLE_MAPS_API_KEY": api_key}
        ... )
        >>> class GoogleMapsTools:
        ...     pass
    
    Note:
        Requires Phase 1C MCP integration to be complete.
        This is a placeholder for future MCP tool registration.
    """
    def decorator(cls_or_func):
        # Store MCP metadata
        mcp_metadata = {
            "server_command": server_command,
            "server_args": server_args,
            "env": env or {},
            "timeout": timeout,
            "is_mcp_tool": True
        }
        
        if isinstance(cls_or_func, type):
            # Class decorator
            cls_or_func._mcp_metadata = mcp_metadata
        else:
            # Function decorator
            cls_or_func._mcp_metadata = mcp_metadata
        
        return cls_or_func
    
    return decorator


def langchain_tool(lc_tool):
    """
    Adapter decorator for LangChain tools.
    
    Wraps a LangChain Tool instance to make it compatible with
    the LocalToolRegistry.
    
    Args:
        lc_tool: LangChain Tool instance
    
    Example:
        >>> from langchain.tools import DuckDuckGoSearchRun
        >>> 
        >>> @langchain_tool
        >>> def search_wrapper():
        ...     return DuckDuckGoSearchRun()
        >>> 
        >>> registry.register_function(search_wrapper)
    
    Note:
        The wrapped function should return a LangChain Tool instance.
        The registry will adapt it automatically.
    """
    def execute_langchain_tool(**kwargs) -> Dict[str, Any]:
        """Execute LangChain tool with standardized output"""
        try:
            # Get the tool instance
            tool_instance = lc_tool() if callable(lc_tool) else lc_tool
            
            # Execute with LangChain's run method
            result = tool_instance.run(**kwargs)
            
            return {
                "status": "success",
                "data": result,
                "tool_type": "langchain"
            }
        except Exception as e:
            return {
                "status": "error",
                "error": str(e),
                "tool_type": "langchain"
            }
    
    # Add tool metadata
    execute_langchain_tool._tool_metadata = {
        "name": getattr(lc_tool, "name", "langchain_tool"),
        "description": getattr(lc_tool, "description", "LangChain tool"),
        "is_langchain": True
    }
    
    execute_langchain_tool.__name__ = getattr(lc_tool, "name", "langchain_tool")
    execute_langchain_tool.__doc__ = getattr(lc_tool, "description", "")
    
    return execute_langchain_tool


def requires_api_key(key_name: str):
    """
    Decorator that checks for required API keys before execution.
    
    Args:
        key_name: Environment variable name for API key
    
    Example:
        >>> @tool
        >>> @requires_api_key("SERPER_API_KEY")
        >>> def web_search(query: str) -> dict:
        ...     # Tool implementation
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            import os
            
            api_key = os.getenv(key_name)
            if not api_key:
                return {
                    "status": "error",
                    "error": f"Missing required API key: {key_name}",
                    "tool": func.__name__
                }
            
            return func(*args, **kwargs)
        
        return wrapper
    
    return decorator


def with_timeout(seconds: int):
    """
    Decorator that adds timeout to tool execution.
    
    Args:
        seconds: Maximum execution time in seconds
    
    Example:
        >>> @tool
        >>> @with_timeout(30)
        >>> def slow_tool(param: str) -> dict:
        ...     # Long-running operation
        ...     pass
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Dict[str, Any]:
            import signal
            
            def timeout_handler(signum, frame):
                raise TimeoutError(f"Tool {func.__name__} exceeded {seconds}s timeout")
            
            # Set alarm
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(seconds)
            
            try:
                result = func(*args, **kwargs)
                signal.alarm(0)  # Cancel alarm
                return result
            except TimeoutError as e:
                return {
                    "status": "error",
                    "error": str(e),
                    "tool": func.__name__
                }
            finally:
                signal.signal(signal.SIGALRM, old_handler)
        
        return wrapper
    
    return decorator
