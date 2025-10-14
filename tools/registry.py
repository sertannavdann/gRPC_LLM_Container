"""
Modern tool registry following Google ADK patterns with full backward compatibility.

This registry bridges the old gRPC-based tool system with the new ADK-style
function tools, providing a unified interface for tool registration and execution.
"""

import inspect
import logging
from typing import Dict, Any, Callable, List, Optional
from datetime import datetime, timedelta

from .base import ToolResult, ToolError, ToolCallable
from .circuit_breaker import CircuitBreaker

logger = logging.getLogger(__name__)


class LocalToolRegistry:
    """
    Unified tool registry supporting multiple registration patterns.
    
    Supports:
    - Python function tools (ADK-style) with @tool decorator
    - Legacy gRPC client tools (backward compatibility)
    - LangChain tool wrappers
    - MCP toolsets (Phase 1C)
    
    Features:
    - Automatic schema extraction from docstrings and type hints
    - Per-tool circuit breakers for reliability
    - OpenAI function calling format export
    - Standardized error handling
    
    Example:
        >>> registry = LocalToolRegistry()
        >>> 
        >>> # Register ADK-style function
        >>> @registry.register
        >>> def web_search(query: str) -> dict:
        ...     '''Search the web.
        ...     
        ...     Args:
        ...         query (str): Search query
        ...     
        ...     Returns:
        ...         Dict with status key
        ...     '''
        ...     return {"status": "success", "results": [...]}
        >>> 
        >>> # Execute tool
        >>> result = registry.call_tool("web_search", query="LangGraph")
    """
    
    def __init__(self, max_failures: int = 3):
        """
        Initialize tool registry.
        
        Args:
            max_failures: Circuit breaker threshold (default: 3)
        """
        self.tools: Dict[str, ToolCallable] = {}
        self.schemas: Dict[str, Dict[str, Any]] = {}
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}
        self.max_failures = max_failures
        self.tool_metadata: Dict[str, Dict[str, Any]] = {}
        
        logger.info(f"LocalToolRegistry initialized (max_failures={max_failures})")
    
    def register(
        self,
        func: Optional[Callable] = None,
        *,
        name: Optional[str] = None,
        description: Optional[str] = None
    ):
        """
        Decorator for registering Python functions as tools.
        
        Automatically extracts schema from function signature and docstring
        following Google ADK patterns.
        
        Args:
            func: Function to register (when used as @register)
            name: Override tool name (default: function name)
            description: Override description (default: from docstring)
        
        Returns:
            Decorated function or decorator
        
        Example:
            >>> @registry.register
            >>> def my_tool(param: str) -> dict:
            ...     return {"status": "success"}
            >>> 
            >>> @registry.register(name="custom_name", description="Custom desc")
            >>> def another_tool(x: int) -> dict:
            ...     return {"status": "success", "data": x * 2}
        """
        def decorator(f: Callable) -> Callable:
            tool_name = name or f.__name__
            
            try:
                # Extract schema from function
                schema = self._extract_schema(f, tool_name, description)
                
                # Register tool
                self.tools[tool_name] = f
                self.schemas[tool_name] = schema
                self.circuit_breakers[tool_name] = CircuitBreaker(
                    max_failures=self.max_failures
                )
                self.tool_metadata[tool_name] = {
                    "type": "function",
                    "registered_at": datetime.now().isoformat()
                }
                
                logger.info(
                    f"Registered function tool '{tool_name}' with "
                    f"{len(schema.get('parameters', {}).get('properties', {}))} parameters"
                )
                
            except Exception as e:
                logger.error(f"Failed to register tool '{tool_name}': {e}")
                raise
            
            return f
        
        # Handle both @register and @register(...) syntax
        if func is None:
            return decorator
        else:
            return decorator(func)
    
    def register_gRPC_tool(
        self,
        name: str,
        client_method: Callable,
        description: str,
        parameters: Optional[Dict[str, Any]] = None
    ):
        """
        Register a legacy gRPC client tool for backward compatibility.
        
        Wraps gRPC client methods to work with the new registry system.
        
        Args:
            name: Tool name
            client_method: gRPC client method (e.g., tool_client.call_tool)
            description: Tool description
            parameters: Optional parameter schema override
        
        Example:
            >>> from shared.clients.tool_client import ToolClient
            >>> tool_client = ToolClient("tool_service", 50053)
            >>> 
            >>> registry.register_gRPC_tool(
            ...     name="web_search",
            ...     client_method=lambda **kw: tool_client.call_tool("web_search", **kw),
            ...     description="Search the web via gRPC service"
            ... )
        """
        # Wrap gRPC method
        def gRPC_wrapper(**kwargs) -> Dict[str, Any]:
            try:
                result = client_method(**kwargs)
                # Ensure standardized format
                if isinstance(result, dict) and "status" in result:
                    return result
                return {"status": "success", "data": result}
            except Exception as e:
                return {"status": "error", "error": str(e), "tool": name}
        
        # Create schema
        schema = {
            "name": name,
            "description": description,
            "parameters": parameters or {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        self.tools[name] = gRPC_wrapper
        self.schemas[name] = schema
        self.circuit_breakers[name] = CircuitBreaker(max_failures=self.max_failures)
        self.tool_metadata[name] = {
            "type": "grpc",
            "registered_at": datetime.now().isoformat()
        }
        
        logger.info(f"Registered gRPC tool '{name}'")
    
    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool with circuit breaker protection.
        
        Args:
            tool_name: Name of tool to execute
            **kwargs: Tool parameters
        
        Returns:
            Standardized result dictionary with "status" key
        
        Example:
            >>> result = registry.call_tool("web_search", query="Python")
            >>> if result["status"] == "success":
            ...     print(result["data"])
        """
        if tool_name not in self.tools:
            logger.warning(f"Tool '{tool_name}' not found")
            return {
                "status": "error",
                "error": f"Tool '{tool_name}' not found",
                "available_tools": self.get_available_tools()
            }
        
        # Check circuit breaker
        breaker = self.circuit_breakers[tool_name]
        if not breaker.is_available():
            logger.warning(f"Circuit breaker open for '{tool_name}' (state: {breaker.state})")
            return {
                "status": "error",
                "error": f"Circuit breaker {breaker.state} for '{tool_name}'",
                "circuit_breaker_metrics": breaker.get_metrics()
            }
        
        # Execute tool
        start_time = datetime.now()
        
        try:
            logger.debug(f"Executing tool '{tool_name}' with args: {kwargs}")
            result = self.tools[tool_name](**kwargs)
            
            # Validate result format
            if not isinstance(result, dict):
                logger.warning(f"Tool '{tool_name}' returned non-dict result, wrapping")
                result = {"status": "success", "data": result}
            
            if "status" not in result:
                result["status"] = "success"
            
            # Record success
            if result["status"] == "success":
                breaker.record_success()
            else:
                breaker.record_failure()
            
            # Add execution metadata
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            result["_metadata"] = {
                "tool_name": tool_name,
                "latency_ms": latency_ms,
                "timestamp": datetime.now().isoformat()
            }
            
            return result
            
        except ToolError as e:
            breaker.record_failure()
            logger.error(f"Tool error in '{tool_name}': {e}")
            return e.to_dict()
            
        except Exception as e:
            breaker.record_failure()
            logger.error(f"Unexpected error in '{tool_name}': {e}", exc_info=True)
            return {
                "status": "error",
                "error": str(e),
                "tool": tool_name,
                "circuit_breaker_metrics": breaker.get_metrics()
            }
    
    def get(self, name: str) -> Optional[ToolCallable]:
        """
        Get tool callable by name (for direct invocation).
        
        Args:
            name: Tool name
        
        Returns:
            Tool callable or None if not found or circuit breaker open
        """
        if name not in self.tools:
            return None
        
        breaker = self.circuit_breakers.get(name)
        if breaker and not breaker.is_available():
            return None
        
        return self.tools[name]
    
    def get_available_tools(self) -> List[str]:
        """
        Get list of tools with closed circuit breakers.
        
        Returns:
            List of available tool names
        """
        available = []
        for name, breaker in self.circuit_breakers.items():
            if breaker.is_available():
                available.append(name)
        return available
    
    def list_all_tools(self) -> List[str]:
        """Get all registered tool names (including circuit-broken)"""
        return list(self.tools.keys())
    
    def reset_circuit_breaker(self, tool_name: str) -> bool:
        """
        Manually reset circuit breaker for a tool.
        
        Args:
            tool_name: Tool name
        
        Returns:
            True if reset successful, False if tool not found
        """
        if tool_name in self.circuit_breakers:
            self.circuit_breakers[tool_name].reset()
            logger.info(f"Reset circuit breaker for '{tool_name}'")
            return True
        return False
    
    def get_circuit_breaker_status(self) -> Dict[str, Dict[str, Any]]:
        """
        Get circuit breaker metrics for all tools.
        
        Returns:
            Dictionary mapping tool names to circuit breaker metrics
        """
        return {
            name: breaker.get_metrics()
            for name, breaker in self.circuit_breakers.items()
        }
    
    def to_openai_tools(self) -> List[Dict[str, Any]]:
        """
        Export tools as OpenAI function calling schema.
        
        Only includes available (non-circuit-broken) tools.
        
        Returns:
            List of OpenAI function schema dictionaries
        
        Example:
            >>> tools_schema = registry.to_openai_tools()
            >>> response = llm.generate(
            ...     messages=messages,
            ...     tools=tools_schema
            ... )
        """
        available_tools = self.get_available_tools()
        
        openai_tools = []
        for tool_name in available_tools:
            schema = self.schemas.get(tool_name)
            if schema:
                openai_tools.append({
                    "type": "function",
                    "function": {
                        "name": schema["name"],
                        "description": schema["description"],
                        "parameters": schema.get("parameters", {
                            "type": "object",
                            "properties": {},
                            "required": []
                        })
                    }
                })
        
        return openai_tools
    
    def _extract_schema(
        self,
        func: Callable,
        name: str,
        description: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Extract tool schema from function signature and docstring.
        
        Follows Google-style docstring format with Args: and Returns: sections.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        
        schema = {
            "name": name,
            "description": description or self._extract_description(doc),
            "parameters": {
                "type": "object",
                "properties": {},
                "required": []
            }
        }
        
        # Extract parameters from signature
        for param_name, param in sig.parameters.items():
            if param_name == "self":
                continue
            
            param_type = self._python_type_to_json_type(param.annotation)
            param_desc = self._extract_param_description(doc, param_name)
            
            schema["parameters"]["properties"][param_name] = {
                "type": param_type,
                "description": param_desc
            }
            
            # Track required parameters (no default value)
            if param.default == inspect.Parameter.empty:
                schema["parameters"]["required"].append(param_name)
        
        return schema
    
    def _extract_description(self, docstring: str) -> str:
        """Extract main description from docstring (before Args:)"""
        lines = docstring.split('\n')
        description = []
        
        for line in lines:
            line = line.strip()
            if any(section in line for section in ['Args:', 'Returns:', 'Raises:', 'Example:']):
                break
            if line:
                description.append(line)
        
        return ' '.join(description) if description else "No description provided"
    
    def _extract_param_description(self, docstring: str, param_name: str) -> str:
        """Extract parameter description from Args: section"""
        in_args = False
        
        for line in docstring.split('\n'):
            line = line.strip()
            
            if 'Args:' in line:
                in_args = True
                continue
            
            if in_args:
                if any(section in line for section in ['Returns:', 'Raises:', 'Example:']):
                    break
                
                # Look for "param_name (type): description" or "param_name: description"
                if param_name in line and ':' in line:
                    # Extract description after colon
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        desc = parts[1].strip()
                        # Remove type annotation if present
                        if desc.startswith('(') and ')' in desc:
                            desc = desc.split(')', 1)[1].strip()
                        return desc
        
        return ""
    
    def _python_type_to_json_type(self, python_type) -> str:
        """Convert Python type hints to JSON schema types"""
        if python_type == inspect.Parameter.empty:
            return "string"
        
        # Direct type mapping
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object"
        }
        
        # Try direct lookup
        if python_type in type_map:
            return type_map[python_type]
        
        # Handle typing module types (List, Dict, Optional, etc.)
        origin = getattr(python_type, '__origin__', None)
        if origin in type_map:
            return type_map[origin]
        
        # Handle string annotations
        if isinstance(python_type, str):
            lower_type = python_type.lower()
            for py_type, json_type in type_map.items():
                if py_type.__name__.lower() in lower_type:
                    return json_type
        
        # Default to string for unknown types
        return "string"
    
    def __repr__(self) -> str:
        total = len(self.tools)
        available = len(self.get_available_tools())
        return f"<LocalToolRegistry: {total} tools ({available} available)>"
    
    def __len__(self) -> int:
        return len(self.tools)
