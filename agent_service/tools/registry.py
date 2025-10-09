"""
LocalToolRegistry - ADK-style tool registration with automatic schema extraction.

This registry manages Python functions as tools, extracting schemas from
docstrings and type hints following Google ADK best practices.
"""

import inspect
import logging
from typing import Dict, Any, Callable, List, Optional

from .base import ToolResult, ToolError

logger = logging.getLogger(__name__)


class LocalToolRegistry:
    """
    ADK-style tool registry with automatic schema extraction.
    
    Features:
    - Auto-extract schemas from function signatures and docstrings
    - Circuit breaker pattern for failing tools
    - Standardized tool execution with error handling
    - Support for required/optional parameters
    """
    
    def __init__(self, max_failures: int = 3):
        """
        Initialize the tool registry.
        
        Args:
            max_failures: Number of failures before circuit breaker trips
        """
        self.tools: Dict[str, Callable] = {}
        self.schemas: Dict[str, Dict] = {}
        self.circuit_breakers: Dict[str, int] = {}
        self.max_failures = max_failures
        
        logger.info(f"LocalToolRegistry initialized (max_failures={max_failures})")
    
    def register_function(self, func: Callable) -> None:
        """
        Register a Python function as a tool.
        
        The function must:
        - Have a docstring with Args: and Returns: sections
        - Have type hints for parameters
        - Return Dict[str, Any] with "status" key
        
        Args:
            func: Python function to register as a tool
        """
        name = func.__name__
        
        try:
            schema = self._extract_schema(func)
            
            self.tools[name] = func
            self.schemas[name] = schema
            self.circuit_breakers[name] = 0
            
            logger.info(f"Registered tool '{name}' with {len(schema.get('parameters', {}))} parameters")
        except Exception as e:
            logger.error(f"Failed to register tool '{name}': {e}")
            raise
    
    def call_tool(self, tool_name: str, **kwargs) -> Dict[str, Any]:
        """
        Execute a tool and return standardized result.
        
        Args:
            tool_name: Name of the tool to execute
            **kwargs: Tool parameters
        
        Returns:
            Dictionary with "status" key ("success" or "error")
        """
        if tool_name not in self.tools:
            logger.warning(f"Tool '{tool_name}' not found")
            return {
                "status": "error",
                "message": f"Tool '{tool_name}' not found"
            }
        
        # Check circuit breaker
        if self.circuit_breakers.get(tool_name, 0) >= self.max_failures:
            logger.warning(f"Circuit breaker open for '{tool_name}'")
            return {
                "status": "error",
                "message": f"Circuit breaker open for '{tool_name}' (too many failures)"
            }
        
        try:
            logger.debug(f"Executing tool '{tool_name}' with args: {kwargs}")
            result = self.tools[tool_name](**kwargs)
            
            # Validate result format
            if isinstance(result, dict) and "status" in result:
                # Success - reset circuit breaker
                if result["status"] == "success":
                    self.circuit_breakers[tool_name] = 0
                return result
            else:
                # Wrap non-standard results
                logger.warning(f"Tool '{tool_name}' returned non-standard result, wrapping")
                return {
                    "status": "success",
                    "data": result
                }
                
        except Exception as e:
            # Record failure
            self.circuit_breakers[tool_name] += 1
            failures = self.circuit_breakers[tool_name]
            
            logger.error(f"Tool '{tool_name}' failed ({failures}/{self.max_failures}): {e}")
            
            return {
                "status": "error",
                "message": str(e),
                "tool": tool_name,
                "failures": failures
            }
    
    def get_available_tools(self) -> List[str]:
        """
        Get list of tools that are not circuit-broken.
        
        Returns:
            List of tool names
        """
        available = [
            name for name, failures in self.circuit_breakers.items()
            if failures < self.max_failures
        ]
        return available
    
    def reset_circuit_breaker(self, tool_name: str) -> bool:
        """
        Reset circuit breaker for a specific tool.
        
        Args:
            tool_name: Name of the tool
        
        Returns:
            True if reset successful, False if tool not found
        """
        if tool_name in self.circuit_breakers:
            self.circuit_breakers[tool_name] = 0
            logger.info(f"Reset circuit breaker for '{tool_name}'")
            return True
        return False
    
    def get_tool_schema(self, tool_name: str) -> Optional[Dict]:
        """Get schema for a specific tool"""
        return self.schemas.get(tool_name)
    
    def _extract_schema(self, func: Callable) -> Dict[str, Any]:
        """
        Extract schema from function signature and docstring.
        
        Parses Google-style docstrings with Args: and Returns: sections.
        """
        sig = inspect.signature(func)
        doc = inspect.getdoc(func) or ""
        
        schema = {
            "name": func.__name__,
            "description": self._extract_description(doc),
            "parameters": {},
            "required": []
        }
        
        # Extract parameters from signature
        for param_name, param in sig.parameters.items():
            param_type = self._python_type_to_json_type(param.annotation)
            param_desc = self._extract_param_description(doc, param_name)
            
            schema["parameters"][param_name] = {
                "type": param_type,
                "description": param_desc
            }
            
            # Track required parameters (those without defaults)
            if param.default == inspect.Parameter.empty:
                schema["required"].append(param_name)
        
        return schema
    
    def _extract_description(self, docstring: str) -> str:
        """Extract main description from docstring (before Args:)"""
        lines = docstring.split('\n')
        description = []
        
        for line in lines:
            line = line.strip()
            if line.startswith('Args:') or line.startswith('Returns:') or line.startswith('Raises:'):
                break
            if line:
                description.append(line)
        
        return ' '.join(description)
    
    def _extract_param_description(self, docstring: str, param_name: str) -> str:
        """Extract parameter description from Args: section"""
        in_args = False
        
        for line in docstring.split('\n'):
            line = line.strip()
            
            if 'Args:' in line:
                in_args = True
                continue
            
            if in_args:
                if 'Returns:' in line or 'Raises:' in line:
                    break
                
                # Look for "param_name (type): description" or "param_name: description"
                if param_name in line and (':' in line or '(' in line):
                    # Extract description after colon
                    parts = line.split(':', 1)
                    if len(parts) > 1:
                        return parts[1].strip()
        
        return ""
    
    def _python_type_to_json_type(self, python_type) -> str:
        """Convert Python type hints to JSON schema types"""
        # Handle None/missing annotation
        if python_type == inspect.Parameter.empty:
            return "string"
        
        # Direct type mapping
        type_map = {
            str: "string",
            int: "integer",
            float: "number",
            bool: "boolean",
            list: "array",
            dict: "object",
            List: "array",
            Dict: "object"
        }
        
        # Try direct lookup
        if python_type in type_map:
            return type_map[python_type]
        
        # Handle typing module types
        origin = getattr(python_type, '__origin__', None)
        if origin in type_map:
            return type_map[origin]
        
        # Default to string for unknown types
        return "string"
    
    def __repr__(self) -> str:
        return f"<LocalToolRegistry: {len(self.tools)} tools, {len(self.get_available_tools())} available>"
