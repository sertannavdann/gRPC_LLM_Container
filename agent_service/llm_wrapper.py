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
                # Don't include tool call JSON in the prompt - it confuses the model
                # The tool results will be included via ToolMessage below
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
            str: Formatted tool descriptions with examples
        """
        tool_descriptions = []
        tool_names = []
        
        for tool in tools:
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            tool_names.append(name)
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
        
        # Create concrete examples based on available tools
        examples = []
        if "web_search" in tool_names:
            examples.append(
                'User: "Search for Python 3.12 release notes"\n'
                'Assistant: {"function_call": {"name": "web_search", "arguments": {"query": "Python 3.12 release notes official"}}}'
            )
        if "math_solver" in tool_names:
            examples.append(
                'User: "What is 15 * 234?"\n'
                'Assistant: {"function_call": {"name": "math_solver", "arguments": {"expression": "15 * 234"}}}'
            )
        if "load_web_page" in tool_names:
            examples.append(
                'User: "Load https://docs.python.org/3/"\n'
                'Assistant: {"function_call": {"name": "load_web_page", "arguments": {"url": "https://docs.python.org/3/"}}}'
            )
        
        examples_text = "\n\n".join(examples) if examples else "See below for format."
        
        return f"""AVAILABLE TOOLS:
{tools_text}

WHEN TO USE TOOLS:
- web_search: For current events, recent information, or specific facts you need to look up
- math_solver: For calculations, equations, or numerical problems
- load_web_page: For fetching content from specific URLs

HOW TO CALL A TOOL:
Respond with ONLY this JSON format (no extra text before or after):
{{"function_call": {{"name": "tool_name", "arguments": {{"param": "value"}}}}}}

EXAMPLES:
{examples_text}

IMPORTANT: 
- If you can answer directly without tools, just respond normally
- If you need a tool, respond ONLY with the JSON (nothing else)
- Use exact parameter names as shown above"""
    
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

        def normalize_args(args):
            if isinstance(args, dict):
                return args
            if isinstance(args, str):
                try:
                    return json.loads(args)
                except Exception:
                    return {"input": args}
            return {}

        # Helper: extract first JSON object if present (tolerate extra text)
        def extract_first_json(text: str) -> Optional[dict]:
            start = text.find("{")
            if start == -1:
                return None
            brace = 0
            in_str = False
            esc = False
            for i in range(start, len(text)):
                ch = text[i]
                if esc:
                    esc = False
                    continue
                if ch == "\\":
                    esc = True
                    continue
                if ch == '"':
                    in_str = not in_str
                    continue
                if not in_str:
                    if ch == '{':
                        brace += 1
                    elif ch == '}':
                        brace -= 1
                        if brace == 0:
                            try:
                                return json.loads(text[start:i+1])
                            except Exception:
                                return None
            return None

        tool_calls: List[Dict] = []

        # Try strict JSON forms first
        parsed = extract_first_json(content)
        if isinstance(parsed, dict):
            # OpenAI-style
            if "function_call" in parsed:
                fc = parsed["function_call"] or {}
                name = fc.get("name", "")
                args = normalize_args(fc.get("arguments", {}))
                tool_calls.append({
                    "id": f"call_{abs(hash(name)) % 100000}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
                return tool_calls

            # Non-standard {"tool_name": "...", "arguments": {...}}
            if "tool_name" in parsed and "arguments" in parsed:
                name = parsed.get("tool_name", "")
                args = normalize_args(parsed.get("arguments", {}))
                tool_calls.append({
                    "id": f"call_{abs(hash(name)) % 100000}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
                return tool_calls

        # Regex fallback for embedded JSON function_call blocks
        fc_pattern = r'\{\s*"function_call"\s*:\s*\{.*?\}\s*\}'
        for match in re.findall(fc_pattern, content, re.DOTALL):
            try:
                fc_obj = json.loads(match)
                fc = fc_obj.get("function_call", {})
                name = fc.get("name", "")
                args = normalize_args(fc.get("arguments", {}))
                tool_calls.append({
                    "id": f"call_{abs(hash(match)) % 100000}",
                    "type": "function",
                    "function": {"name": name, "arguments": args},
                })
            except Exception:
                continue

        # Fallback: name(args) textual pattern
        if not tool_calls and tools:
            tool_names = [t["function"]["name"] for t in tools]
            for tool_name in tool_names:
                pattern = rf'{tool_name}\s*\(([^)]*)\)'
                for m in re.findall(pattern, content):
                    try:
                        args: Dict[str, str] = {}
                        if m.strip():
                            for arg in m.split(","):
                                if "=" in arg:
                                    k, v = arg.split("=", 1)
                                    args[k.strip()] = v.strip().strip("'\"")
                        tool_calls.append({
                            "id": f"call_{abs(hash(m)) % 100000}",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": args},
                        })
                    except Exception:
                        continue

        return tool_calls
    
    def close(self):
        """Close gRPC client connection."""
        if hasattr(self.client, "close"):
            self.client.close()
            logger.info("LLMClientWrapper closed")
