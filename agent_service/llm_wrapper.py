"""
Wrapper adapting gRPC LLMClient to LlamaEngine interface.

Allows AgentWorkflow to use remote LLM service via gRPC while
maintaining interface compatibility with the expected LLM engine API.

Example:
    >>> from shared.clients.llm_client import LLMClient
    >>> client = LLMClient(host="localhost", port=50051)
    >>> wrapper = LLMClientWrapper(client)
    >>> response = wrapper.generate(
    ...     messages=[HumanMessage("Hello")],
    ...     temperature=0.7
    ... )
"""

import json
import logging
import re
from typing import List, Dict, Any, Optional

from langchain_core.messages import (
    BaseMessage,
    HumanMessage,
    AIMessage,
    SystemMessage,
    ToolMessage,
    FunctionMessage,
)

logger = logging.getLogger(__name__)


class LLMClientWrapper:
    """
    Adapts gRPC LLMClient to LlamaEngine interface expected by AgentWorkflow.
    
    Translates between:
    - LangChain BaseMessage format → string prompt for gRPC
    - gRPC text response → structured response with tool_calls
    
    The wrapper handles:
    1. Message history formatting (system, user, assistant, tool)
    2. Tool schema injection into prompts
    3. Function call extraction from LLM responses
    4. Error handling and retries
    
    Attributes:
        client: gRPC LLMClient instance
        default_temperature: Default sampling temperature
        default_max_tokens: Default max tokens to generate
    
    Example:
        >>> wrapper = LLMClientWrapper(llm_client)
        >>> response = wrapper.generate(
        ...     messages=[HumanMessage("What is 2+2?")],
        ...     tools=[{"function": {"name": "math_solver", ...}}],
        ...     temperature=0.7
        ... )
        >>> print(response["content"])
    """
    
    def __init__(
        self,
        client,  # LLMClient instance
        default_temperature: float = 0.7,
        default_max_tokens: int = 512,
    ):
        """
        Initialize wrapper with gRPC client.
        
        Args:
            client: LLMClient instance connected to llm_service
            default_temperature: Default sampling temperature
            default_max_tokens: Default maximum tokens
        """
        self.client = client
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens
        
        logger.info(
            f"LLMClientWrapper initialized: "
            f"temp={default_temperature}, "
            f"max_tokens={default_max_tokens}"
        )
    
    def generate(
        self,
        messages: List[BaseMessage],
        tools: Optional[List[Dict]] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stream: bool = False,
    ) -> Dict[str, Any]:
        """
        Generate response via gRPC LLM service.
        
        Args:
            messages: LangChain message history
            tools: OpenAI-format tool schemas (optional)
            temperature: Sampling temperature (uses default if None)
            max_tokens: Maximum tokens to generate (uses default if None)
            stream: Whether to stream response (not yet fully supported)
        
        Returns:
            dict: Response with:
                - content: Text content (empty if tool_calls present)
                - tool_calls: List of function calls (empty if no calls)
                - model: Model name
                - finish_reason: Completion reason
        
        Example:
            >>> response = wrapper.generate(
            ...     messages=[HumanMessage("Calculate 5*5")],
            ...     tools=[math_solver_schema],
            ...     temperature=0.5
            ... )
            >>> if response["tool_calls"]:
            ...     print("Tool called:", response["tool_calls"][0]["function"]["name"])
        """
        # Use defaults if not provided
        temp = temperature if temperature is not None else self.default_temperature
        max_tok = max_tokens if max_tokens is not None else self.default_max_tokens
        
        # Format messages to prompt string
        prompt = self._format_messages(messages, tools)
        
        logger.debug(
            f"Generating response: "
            f"messages={len(messages)}, "
            f"tools={len(tools) if tools else 0}, "
            f"temp={temp}, "
            f"max_tokens={max_tok}"
        )
        
        try:
            # Call gRPC service - returns a string directly
            response_text = self.client.generate(
                prompt=prompt,
                temperature=temp,
                max_tokens=max_tok,
            )
            
            # Extract text from response (it's already a string)
            content = response_text.strip() if isinstance(response_text, str) else ""
            
            # Try to extract function calls from content
            tool_calls = self._extract_tool_calls(content, tools)
            
            # If tool calls found, clear content (OpenAI convention)
            if tool_calls:
                logger.info(f"Extracted {len(tool_calls)} tool calls from response")
                content = ""
            
            result = {
                "content": content,
                "tool_calls": tool_calls,
                "model": "qwen2.5",  # Fixed model name
                "finish_reason": "tool_calls" if tool_calls else "stop",
            }
            
            logger.debug(
                f"Response generated: "
                f"content_len={len(result['content'])}, "
                f"tool_calls={len(result['tool_calls'])}"
            )
            
            return result
        
        except Exception as e:
            logger.error(f"Error generating response: {e}", exc_info=True)
            # Return error response
            return {
                "content": f"Error: {str(e)}",
                "tool_calls": [],
                "model": "error",
                "finish_reason": "error",
            }
    
    def _format_messages(
        self,
        messages: List[BaseMessage],
        tools: Optional[List[Dict]] = None,
    ) -> str:
        """
        Convert LangChain messages to prompt string.
        
        Formats messages with role prefixes and injects tool schemas
        if provided.
        
        Args:
            messages: LangChain message history
            tools: Optional tool schemas
        
        Returns:
            str: Formatted prompt string
        """
        parts = []
        
        for msg in messages:
            if isinstance(msg, SystemMessage):
                parts.append(f"System: {msg.content}\n")
            elif isinstance(msg, HumanMessage):
                parts.append(f"User: {msg.content}\n")
            elif isinstance(msg, AIMessage):
                # Handle both content and function calls
                if msg.content:
                    parts.append(f"Assistant: {msg.content}\n")
                # Check for function calls in additional_kwargs
                if msg.additional_kwargs.get("tool_calls"):
                    tool_calls = msg.additional_kwargs["tool_calls"]
                    parts.append(f"Assistant: [Called tools: {json.dumps(tool_calls)}]\n")
            elif isinstance(msg, (ToolMessage, FunctionMessage)):
                # Include tool results
                parts.append(f"Tool Result: {msg.content}\n")
        
        prompt = "".join(parts)
        
        # Add tool schemas if provided
        if tools:
            tool_section = self._format_tool_schemas(tools)
            prompt = f"{tool_section}\n\n{prompt}"
        
        # Add assistant prompt
        prompt += "Assistant:"
        
        return prompt
    
    def _format_tool_schemas(self, tools: List[Dict]) -> str:
        """
        Format tool schemas for prompt injection.
        
        Args:
            tools: OpenAI-format tool schemas
        
        Returns:
            str: Formatted tool descriptions
        """
        tool_descriptions = []
        
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            description = func.get("description", "No description")
            parameters = func.get("parameters", {})
            
            # Format parameters
            param_list = []
            if "properties" in parameters:
                for param_name, param_info in parameters["properties"].items():
                    param_type = param_info.get("type", "any")
                    param_desc = param_info.get("description", "")
                    required = param_name in parameters.get("required", [])
                    req_marker = " (required)" if required else " (optional)"
                    param_list.append(
                        f"  - {param_name} ({param_type}){req_marker}: {param_desc}"
                    )
            
            tool_desc = f"Tool: {name}\n{description}"
            if param_list:
                tool_desc += "\nParameters:\n" + "\n".join(param_list)
            
            tool_descriptions.append(tool_desc)
        
        tools_text = "\n\n".join(tool_descriptions)
        
        return f"""Available Tools:
{tools_text}

To use a tool, respond with a JSON function call in this format:
{{"function_call": {{"name": "tool_name", "arguments": {{"param": "value"}}}}}}"""
    
    def _extract_tool_calls(
        self,
        content: str,
        tools: Optional[List[Dict]] = None,
    ) -> List[Dict]:
        """
        Extract function calls from LLM response.
        
        Looks for JSON function call patterns in response text.
        Supports both single and multiple function calls.
        
        Args:
            content: LLM response text
            tools: Available tool schemas (for validation)
        
        Returns:
            list[dict]: Extracted function calls in OpenAI format
        """
        if not content:
            return []
        
        tool_calls = []
        
        # Pattern 1: Look for explicit function_call JSON
        # {"function_call": {"name": "tool_name", "arguments": {...}}}
        fc_pattern = r'\{"function_call":\s*\{[^}]+\}\}'
        matches = re.findall(fc_pattern, content, re.DOTALL)
        
        for match in matches:
            try:
                fc_obj = json.loads(match)
                if "function_call" in fc_obj:
                    func_call = fc_obj["function_call"]
                    
                    # Create OpenAI-format tool call
                    tool_call = {
                        "id": f"call_{hash(match) % 100000}",
                        "type": "function",
                        "function": {
                            "name": func_call.get("name", ""),
                            "arguments": func_call.get("arguments", {}),
                        },
                    }
                    tool_calls.append(tool_call)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse function call: {match}")
        
        # Pattern 2: Look for tool_name(args) format
        # e.g., "math_solver(expression='2+2')"
        if not tool_calls and tools:
            tool_names = [t["function"]["name"] for t in tools]
            for tool_name in tool_names:
                # Look for tool_name(...) pattern
                pattern = rf'{tool_name}\s*\(([^)]+)\)'
                matches = re.findall(pattern, content)
                
                for match in matches:
                    try:
                        # Parse arguments (simple key=value format)
                        args = {}
                        for arg in match.split(","):
                            arg = arg.strip()
                            if "=" in arg:
                                key, value = arg.split("=", 1)
                                key = key.strip()
                                value = value.strip().strip("'\"")
                                args[key] = value
                        
                        tool_call = {
                            "id": f"call_{hash(match) % 100000}",
                            "type": "function",
                            "function": {
                                "name": tool_name,
                                "arguments": args,
                            },
                        }
                        tool_calls.append(tool_call)
                    except Exception as e:
                        logger.warning(f"Failed to parse tool call: {e}")
        
        return tool_calls
    
    def close(self):
        """Close gRPC client connection."""
        if hasattr(self.client, "close"):
            self.client.close()
            logger.info("LLMClientWrapper closed")
