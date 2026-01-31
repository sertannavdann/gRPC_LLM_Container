"""
Orchestrator gRPC service - Unified agent coordination service.

Combines agent_service and routing logic into a single orchestrator that:
- Routes queries to appropriate tools/services  
- Manages agent workflows
- Handles conversation persistence
- Provides crash recovery

This replaces the separate agent_service + llm_service split with a
unified orchestration layer.
"""

import uuid
import json
import time
import logging
from concurrent import futures
from typing import Optional, Dict, Any

import grpc
from grpc_reflection.v1alpha import reflection
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

# Import configuration
from .config import OrchestratorConfig

# These will be copied from agent_service
from shared.clients.llm_client import LLMClient
from core.checkpointing import CheckpointManager, RecoveryManager
from core import AgentWorkflow, WorkflowConfig
from core.state import create_initial_state
from core.self_consistency import SelfConsistencyVerifier
from tools.registry import LocalToolRegistry
from tools.builtin.web_search import web_search
from tools.builtin.math_solver import math_solver  
from tools.builtin.web_loader import load_web_page
from tools.builtin.code_executor import execute_code, set_sandbox_client
from tools.builtin.user_context import get_user_context, get_daily_briefing, get_commute_time

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# New imports for Registry and Worker clients
from shared.clients.registry_client import RegistryClient
from shared.clients.worker_client import WorkerClient
from shared.clients.sandbox_client import SandboxClient

# Provider system imports
from shared.providers import (
    setup_providers,
    get_provider,
    ProviderConfig,
    ProviderType,
    ChatRequest,
    ChatMessage,
    BaseProvider,
)

import os
import asyncio
import threading

# Protobuf imports
from shared.generated import agent_pb2
from shared.generated import agent_pb2_grpc


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestrator")


class OnlineProviderWrapper:
    """
    Thread-safe wrapper that adapts async OnlineProvider interface to sync LLMClient interface.

    This enables seamless switching between local gRPC-based LLM and cloud APIs
    (Perplexity, OpenAI, Anthropic) without changing the orchestrator code.

    Uses thread-local event loops to ensure thread safety when called from
    multiple gRPC worker threads concurrently.
    """

    def __init__(
        self,
        provider: BaseProvider,
        model: str,
        temperature: float = 0.7,
    ):
        """
        Initialize the wrapper.

        Args:
            provider: Online provider instance (PerplexityProvider, OpenAIProvider, etc.)
            model: Model name to use for completions
            temperature: Default temperature setting
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature
        # Thread-local storage for event loops (thread-safe with concurrent requests)
        self._thread_local = threading.local()
        logger.info(f"OnlineProviderWrapper initialized: model={model}, temp={temperature}")

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        """Get or create thread-local event loop."""
        if not hasattr(self._thread_local, 'loop') or self._thread_local.loop.is_closed():
            self._thread_local.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._thread_local.loop)
        return self._thread_local.loop

    def _run_async(self, coro):
        """Run async coroutine in thread-local event loop.

        Wraps coroutine in a task to ensure proper async context
        for aiohttp's timeout context manager.
        """
        loop = self._get_loop()
        # Wrap in task to ensure proper async context for aiohttp timeout
        task = loop.create_task(coro)
        return loop.run_until_complete(task)
    
    def generate(
        self,
        prompt: str,
        max_tokens: int = 2048,
        temperature: float = None,
        response_format: str = None,
    ) -> str:
        """
        Generate completion using online provider.
        
        Matches LLMClient.generate() interface.
        
        Args:
            prompt: The prompt text
            max_tokens: Maximum tokens to generate
            temperature: Temperature override
            response_format: Format hint (e.g., "json")
            
        Returns:
            Generated text content
        """
        temp = temperature if temperature is not None else self.temperature
        
        # Build ChatRequest
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model=self.model,
            temperature=temp,
            max_tokens=max_tokens,
        )
        
        if response_format == "json":
            request.extra["response_format"] = {"type": "json_object"}
        
        # Run async generate
        response = self._run_async(self.provider.generate(request))
        
        return response.content
    
    def generate_stream(self, prompt: str, max_tokens: int = 2048, temperature: float = None):
        """
        Generate streaming completion using online provider.
        
        Matches LLMClient.generate_stream() interface.
        
        Note: Returns a generator that yields response-like objects with 'token' and 'is_final'.
        """
        temp = temperature if temperature is not None else self.temperature
        
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model=self.model,
            temperature=temp,
            max_tokens=max_tokens,
            stream=True,
        )
        
        # For streaming, we need to adapt the async iterator
        # This is a simplified implementation - yields tokens as they come
        async def _stream():
            collected = []
            async for token in self.provider.generate_stream(request):
                collected.append(token)
                yield token
        
        # Run in sync context
        class StreamResponse:
            def __init__(self, token, is_final=False):
                self.token = token
                self.is_final = is_final
        
        async def collect_stream():
            tokens = []
            async for token in self.provider.generate_stream(request):
                tokens.append(StreamResponse(token, False))
            if tokens:
                tokens[-1].is_final = True
            return tokens
        
        results = self._run_async(collect_stream())
        for r in results:
            yield r


class LLMEngineWrapper:
    """
    Wrapper around LLM client with structured tool calling support.
    
    Implements Agent0-style multi-turn rollouts where the LLM can:
    1. Generate reasoning text
    2. Emit code blocks for execution
    3. See execution results
    4. Continue reasoning with updated context
    """
    
    def __init__(
        self,
        llm_client: LLMClient,
        temperature: float = 0.7,
        max_tokens: int = 512,
        max_tool_iterations: int = 5,
        sandbox_client = None  # Optional SandboxClient for code execution
    ):
        self.client = llm_client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_iterations = max_tool_iterations
        self.sandbox_client = sandbox_client
        logger.debug(
            f"LLMEngineWrapper initialized: temp={temperature}, "
            f"max_tokens={max_tokens}, max_tool_iterations={max_tool_iterations}"
        )
    
    def generate(self, messages: list, tools: list = None, temperature: float = None, 
                 max_tokens: int = None, stream: bool = False) -> dict:
        """
        Generate response from LLM with optional tool calling.
        
        Args:
            messages: List of LangChain message objects OR message dicts with 'role' and 'content'
            tools: Optional list of tool schemas (None = no tools, [] = no tools, [schemas] = with tools)
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            stream: Whether to stream response (not implemented)
        
        Returns:
            dict with 'content' and optionally 'tool_calls'
        """
        logger.debug(f"LLMEngineWrapper.generate() called with {len(messages)} messages, {len(tools) if tools else 0} tools")
        
        # Use provided values or defaults
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        
        # Route to appropriate generation method
        if tools and len(tools) > 0:
            return self._generate_with_tools(messages, tools, temp, max_tok)
        else:
            return self._generate_direct(messages, temp, max_tok)
    
    def _generate_direct(self, messages: list, temperature: float, max_tokens: int) -> dict:
        """Generate direct response without tools."""
        prompt = self._format_messages(messages)
        
        if not prompt.strip():
            logger.warning("Empty prompt generated from messages")
            return {
                "content": "I received an empty message. Please try again.",
                "tool_calls": []
            }
        
        try:
            response_text = self.client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            
            return {
                "content": response_text.strip(),
                "tool_calls": []
            }
        except Exception as e:
            logger.error(f"Direct generation error: {e}")
            return {
                "content": "Sorry, I encountered an error generating a response.",
                "tool_calls": []
            }
    
    def _generate_with_tools(self, messages: list, tools: list, temperature: float, max_tokens: int) -> dict:
        """
        Generate response with tool calling using Agent0-style multi-turn rollouts.
        
        Implements stop-and-go execution:
        1. LLM generates text + optional tool call
        2. If tool call detected, execute and append result
        3. Continue generation with updated context
        4. Repeat until final answer or max iterations
        """
        import re
        
        # Format tools for prompt
        tools_desc = self._format_tools_description(tools)
        
        # Build conversation history including tool results
        conversation = self._format_messages_with_tools(messages)
        
        # Check if we have tool results in the messages (second call after tool execution)
        has_tool_results = any(isinstance(m, ToolMessage) for m in messages)
        logger.debug(f"Message types: {[type(m).__name__ for m in messages]}")
        logger.debug(f"has_tool_results={has_tool_results} (messages count: {len(messages)})")
        
        # Track multi-turn context
        rollout_context = conversation
        tool_calls_made = []
        iteration = 0
        
        while iteration < self.max_tool_iterations:
            iteration += 1
            
            # Adjust instructions based on whether we have tool results
            if has_tool_results:
                # We have tool results - check if we have ALL the info needed
                prompt = f"""You are a helpful AI assistant with access to tools.

Available tools:
{tools_desc}

Conversation with tool results:
{rollout_context}

Instructions:
1. Review the user's ORIGINAL question and the tool results above
2. If you have ALL the information needed to fully answer the user's question, respond with: {{"type": "answer", "content": "your complete answer"}}
3. If you need MORE information that another tool can provide, call that tool: {{"type": "tool_call", "tool": "tool_name", "arguments": {{...}}}}

IMPORTANT: 
- If user asked about BOTH schedule AND commute, you need results from BOTH get_user_context AND get_commute_time
- Only give a final answer when you have all needed information
- Respond with ONLY valid JSON

Your response (JSON only):"""
            else:
                # First iteration: Determine if tools needed
                prompt = f"""You are a helpful AI assistant with access to tools.

Available tools:
{tools_desc}

Instructions:
- Analyze the user's question to extract relevant values
- To use a tool, respond with ONLY valid JSON in this exact format: {{"type": "tool_call", "tool": "tool_name", "arguments": {{"param_name": "actual_value_from_query"}}}}
- To answer directly without tools, respond with ONLY valid JSON: {{"type": "answer", "content": "your answer here"}}
- IMPORTANT: Extract actual values from the user's question - do NOT use parameter names as values
- For example, if user asks "how long to the office?", use {{"type": "tool_call", "tool": "get_commute_time", "arguments": {{"destination": "office"}}}}
- If user asks "what's my schedule?", use {{"type": "tool_call", "tool": "get_user_context", "arguments": {{"categories": ["calendar"]}}}}
- If no tool is needed, provide a direct answer

Conversation:
{rollout_context}

Your response (JSON only):"""

            logger.debug(f"Multi-turn iteration {iteration}: prompt length={len(prompt)}")
            
            try:
                # Generate with JSON grammar constraint
                response_text = self.client.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format="json"
                )
                
                # Parse response
                parsed = self._parse_tool_response(response_text)
                
                # Check if this is a final answer
                if not parsed.get("tool_calls"):
                    # No tool calls = final answer
                    logger.info(f"✓ Final answer after {iteration} iteration(s), {len(tool_calls_made)} tool call(s)")
                    return {
                        "content": parsed.get("content", ""),
                        "tool_calls": [],
                        "_multi_turn_metadata": {
                            "iterations": iteration,
                            "tool_calls_made": tool_calls_made
                        }
                    }
                
                # Tool call detected - record it
                tool_call = parsed["tool_calls"][0]
                tool_name = tool_call["function"]["name"]
                tool_args = tool_call["function"]["arguments"]
                
                logger.info(f"[Iteration {iteration}] Tool call: {tool_name}({list(tool_args.keys())})")
                tool_calls_made.append({"tool": tool_name, "arguments": tool_args})
                
                # Return tool call for external execution (single-turn mode for compatibility)
                # The graph's tools_node will execute it and feed back results
                if iteration == 1:
                    # First iteration: return tool call for graph to handle
                    return parsed
                
                # Multi-turn: append tool call to context and continue
                rollout_context += f"\nAssistant: [Calling tool: {tool_name} with {tool_args}]"
                rollout_context += f"\nTool Result ({tool_name}): Awaiting execution..."
                
            except Exception as e:
                logger.error(f"Multi-turn iteration {iteration} error: {e}", exc_info=True)
                break
        
        # Max iterations reached
        logger.warning(f"Max tool iterations ({self.max_tool_iterations}) reached")
        return {
            "content": "I attempted to use tools but reached the maximum number of iterations. Please try rephrasing your question.",
            "tool_calls": [],
            "_multi_turn_metadata": {
                "iterations": iteration,
                "tool_calls_made": tool_calls_made,
                "max_iterations_reached": True
            }
        }
    
    def _parse_tool_response(self, response_text: str) -> dict:
        """Parse LLM's JSON response into content or tool_calls."""
        import re
        
        try:
            # Clean response text
            response_text = response_text.strip()
            logger.debug(f"Raw LLM response length={len(response_text)}, first 500 chars: {response_text[:500] if response_text else '(empty)'}")
            
            # Remove markdown code blocks if present (e.g., ```json {...} ```)
            code_block_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', response_text, re.DOTALL)
            if code_block_match:
                logger.debug("Extracted JSON from markdown code block")
                response_text = code_block_match.group(1).strip()
            
            # Try to extract JSON from mixed response (JSON + text)
            # Find the first complete JSON object by matching braces
            json_start = response_text.find('{')
            if json_start != -1:
                # Count braces to find complete JSON object
                brace_count = 0
                json_end = -1
                for i, char in enumerate(response_text[json_start:]):
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            json_end = json_start + i + 1
                            break
                
                if json_end > json_start:
                    json_str = response_text[json_start:json_end]
                    # Check if there's extra text before or after JSON
                    before_json = response_text[:json_start].strip()
                    after_json = response_text[json_end:].strip()
                    
                    if before_json or after_json:
                        logger.warning(f"Extra text found around JSON, extracting JSON only")
                        if after_json:
                            logger.debug(f"Text after JSON: {after_json[:100]}...")
                    
                    response_text = json_str

            # Normalize Python-style booleans (True/False/None) to JSON (true/false/null)
            # LLMs sometimes return Python syntax instead of proper JSON
            import re as re_mod
            response_text = re_mod.sub(r'\bTrue\b', 'true', response_text)
            response_text = re_mod.sub(r'\bFalse\b', 'false', response_text)
            response_text = re_mod.sub(r'\bNone\b', 'null', response_text)

            parsed = json.loads(response_text)
            
            response_type = parsed.get("type", "answer")
            
            if response_type == "tool_call":
                # Extract tool call
                tool_name = parsed.get("tool", "")
                tool_args = parsed.get("arguments", {})
                
                if not tool_name:
                    logger.warning("Tool call missing 'tool' field, treating as direct answer")
                    return {
                        "content": "I tried to use a tool but the request was incomplete. Let me answer directly.",
                        "tool_calls": []
                    }
                
                # Create OpenAI-style tool call
                tool_call = {
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_args
                    }
                }
                
                logger.info(f"✓ Tool call parsed: {tool_name}({list(tool_args.keys())})")
                
                return {
                    "content": "",  # No text content when tool calling
                    "tool_calls": [tool_call]
                }
            
            else:  # type == "answer" or default
                content = parsed.get("content", "")
                return {
                    "content": content,
                    "tool_calls": []
                }
        
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse LLM response as JSON: {e}")
            logger.debug(f"Raw response: {response_text[:200]}")
            
            # Fallback: treat as plain text
            return {
                "content": response_text,
                "tool_calls": []
            }
    
    def _format_tools_description(self, tools: list) -> str:
        """Format tools as readable list for LLM prompt."""
        lines = []
        for i, tool in enumerate(tools, 1):
            func = tool.get("function", {})
            name = func.get("name", "unknown")
            desc = func.get("description", "No description")
            params = func.get("parameters", {}).get("properties", {})
            
            param_list = ", ".join(params.keys()) if params else "none"
            lines.append(f"{i}. {name}: {desc}")
            lines.append(f"   Parameters: {param_list}")
        
        return "\n".join(lines)
    
    def _format_messages(self, messages: list) -> str:
        """Convert messages to simple prompt string."""
        from langchain_core.messages import ToolMessage, SystemMessage
        
        prompt = ""
        for msg in messages:
            if isinstance(msg, HumanMessage):
                prompt += f"User: {msg.content}\n"
            elif isinstance(msg, AIMessage):
                prompt += f"Assistant: {msg.content}\n"
            elif isinstance(msg, SystemMessage):
                prompt += f"System: {msg.content}\n"
            elif isinstance(msg, ToolMessage):
                # Handle tool results
                prompt += f"Tool Result: {msg.content}\n"
            elif isinstance(msg, dict):
                role = msg.get("role", "user")
                content = msg.get("content", "")
                prompt += f"{role.capitalize()}: {content}\n"
            else:
                prompt += f"System: {str(msg.content)}\n"
        
        return prompt.strip()
    
    def _format_messages_with_tools(self, messages: list) -> str:
        """Format messages including tool calls and results for conversation history."""
        from langchain_core.messages import ToolMessage, SystemMessage
        
        lines = []
        
        for msg in messages:
            if isinstance(msg, HumanMessage):
                lines.append(f"User: {msg.content}")
            
            elif isinstance(msg, AIMessage):
                # Check for tool calls in additional_kwargs
                tool_calls = msg.additional_kwargs.get("tool_calls", [])
                if tool_calls:
                    # Show that assistant called a tool
                    for tc in tool_calls:
                        tool_name = tc.get("function", {}).get("name", "unknown")
                        tool_args = tc.get("function", {}).get("arguments", {})
                        lines.append(f"Assistant: [Calling tool: {tool_name} with {tool_args}]")
                elif msg.content:
                    lines.append(f"Assistant: {msg.content}")
            
            elif isinstance(msg, ToolMessage):
                # Show tool result
                tool_name = getattr(msg, 'name', 'unknown_tool')
                lines.append(f"Tool Result ({tool_name}): {msg.content}")
            
            elif isinstance(msg, SystemMessage):
                lines.append(f"System: {msg.content}")
        
        return "\n".join(lines)
    
    def invoke(self, messages: list, **kwargs) -> AIMessage:
        """
        Invoke LLM with messages and return AI response.
        
        Args:
            messages: List of LangChain messages
            **kwargs: Additional parameters (tools, temperature, etc.)
        
        Returns:
            AIMessage with LLM response
        """
        # Convert LangChain messages to format expected by LLM service
        formatted_messages = []
        for msg in messages:
            if isinstance(msg, HumanMessage):
                formatted_messages.append({
                    "role": "user",
                    "content": msg.content
                })
            elif isinstance(msg, AIMessage):
                formatted_messages.append({
                    "role": "assistant", 
                    "content": msg.content
                })
            else:
                formatted_messages.append({
                    "role": "system",
                    "content": str(msg.content)
                })
        
        # Extract tools if provided
        tools = kwargs.get("tools", [])
        temperature = kwargs.get("temperature", self.temperature)
        
        # Use generate method
        response = self.generate(
            messages=formatted_messages,
            tools=tools,
            temperature=temperature,
            max_tokens=self.max_tokens
        )
        
        # Parse response and create AIMessage
        content = response.get("content", "")
        tool_calls = response.get("tool_calls", [])
        
        # Create AI message with tool calls if present
        ai_message = AIMessage(content=content)
        if tool_calls:
            ai_message.additional_kwargs = {"tool_calls": tool_calls}
        
        return ai_message


class OrchestratorService(agent_pb2_grpc.AgentServiceServicer):
    """
    Unified orchestrator service combining agent workflow and routing.
    
    Acts as the Supervisor in the Supervisor-Worker architecture.
    Supports multiple LLM providers (local, perplexity, openai, anthropic).
    """
    
    def __init__(self, config: OrchestratorConfig = None):
        self.config = config or OrchestratorConfig.from_env()
        logger.info("Initializing Orchestrator on 0.0.0.0:50054")
        
        # Initialize provider system
        setup_providers()
        logger.info(f"Provider type: {self.config.provider_type}")
        
        # Initialize LLM provider based on config
        self.llm_client = self._initialize_provider()
        
        # Initialize Sandbox Client
        try:
            self.sandbox_client = SandboxClient(
                host=self.config.sandbox_host,
                port=self.config.sandbox_port
            )
            # Wire sandbox client to code_executor tool
            set_sandbox_client(self.sandbox_client)
            logger.info(f"Sandbox client connected to {self.config.sandbox_host}:{self.config.sandbox_port}")
        except Exception as e:
            logger.warning(f"Sandbox client initialization failed: {e}. Code execution disabled.")
            self.sandbox_client = None
        
        # Initialize Registry Client
        registry_host = os.getenv("REGISTRY_HOST", "registry_service")
        registry_port = int(os.getenv("REGISTRY_PORT", "50055"))
        self.registry_client = RegistryClient(host=registry_host, port=registry_port)
        
        # Initialize Self-Consistency Verifier (Agent0 Phase 2)
        self.self_consistency_verifier = None
        if self.config.enable_self_consistency:
            self.self_consistency_verifier = SelfConsistencyVerifier(
                llm_client=self.llm_client,
                num_samples=self.config.self_consistency_samples,
                consistency_threshold=self.config.self_consistency_threshold
            )
            logger.info(f"Self-consistency enabled: k={self.config.self_consistency_samples}, threshold={self.config.self_consistency_threshold}")
        
        # Initialize LLM Engine Wrapper with multi-turn support
        self.llm_engine = LLMEngineWrapper(
            self.llm_client, 
            temperature=self.config.temperature,
            max_tokens=512,
            max_tool_iterations=self.config.max_iterations,
            sandbox_client=self.sandbox_client
        )
        
        # Initialize Tool Registry
        self.tool_registry = LocalToolRegistry()
        
        # Register built-in tools
        self.tool_registry.register(web_search)
        self.tool_registry.register(math_solver)
        self.tool_registry.register(load_web_page)
        
        # Register user context tools for personalized assistance
        self.tool_registry.register(get_user_context)
        self.tool_registry.register(get_daily_briefing)
        self.tool_registry.register(get_commute_time)
        
        # Register code executor if sandbox is available
        if self.sandbox_client:
            self.tool_registry.register(execute_code)
            logger.info("Code executor tool registered")
        
        # Register delegation tool
        self.tool_registry.register(self.delegate_to_worker)
        
        logger.info(f"Total tools registered: {len(self.tool_registry.tools)}")
    
        # Initialize Checkpoint Manager
        self.checkpoint_manager = CheckpointManager(self.config.checkpoint_db_path)
        self.checkpointer = self.checkpoint_manager.create_checkpointer()
        
        # Initialize workflow config
        self.workflow_config = WorkflowConfig(
            max_iterations=self.config.max_iterations,
            context_window=self.config.context_window,
            temperature=self.config.temperature,
            model_name=self.config.model_name,
            enable_streaming=self.config.enable_streaming,
            max_tool_calls_per_turn=self.config.max_tool_calls_per_turn,
            timeout_seconds=self.config.timeout_seconds
        )
        
        # Initialize agent workflow
        self.workflow = AgentWorkflow(
            tool_registry=self.tool_registry,
            llm_engine=self.llm_engine,
            config=self.workflow_config
        )
        
        # Compile workflow with checkpointing
        self.compiled_workflow = self.workflow.compile(checkpointer=self.checkpointer)
        logger.info("AgentWorkflow compiled with checkpointing")
        
        # Initialize recovery manager
        self.recovery_manager = RecoveryManager(self.checkpoint_manager)
        
        # Run startup recovery
        self._run_startup_recovery()
        
        logger.info("Orchestrator initialization complete")
    
    def _initialize_provider(self):
        """
        Initialize LLM provider based on config.
        
        Returns appropriate provider instance (local gRPC client or online API client).
        For online providers (perplexity, openai, anthropic), returns a wrapper that
        exposes the same interface as LLMClient.
        """
        provider_type = self.config.provider_type.lower()
        
        if provider_type == "local":
            # Use local llama.cpp via gRPC
            logger.info(f"Using LOCAL provider: {self.config.llm_host}:{self.config.llm_port}")
            return LLMClient(host=self.config.llm_host, port=self.config.llm_port)
        
        # Map string to ProviderType enum
        provider_type_map = {
            "perplexity": ProviderType.PERPLEXITY,
            "openai": ProviderType.OPENAI,
            "anthropic": ProviderType.ANTHROPIC,
        }
        
        if provider_type not in provider_type_map:
            logger.warning(f"Unknown provider type '{provider_type}', falling back to local")
            return LLMClient(host=self.config.llm_host, port=self.config.llm_port)
        
        # Check API key
        if not self.config.provider_api_key:
            logger.warning(f"No API key for {provider_type}, falling back to local")
            return LLMClient(host=self.config.llm_host, port=self.config.llm_port)
        
        # Create online provider config
        provider_config = ProviderConfig(
            provider_type=provider_type_map[provider_type],
            api_key=self.config.provider_api_key,
            base_url=self.config.provider_base_url,
            timeout=self.config.provider_timeout,
        )
        
        # Get provider instance
        provider = get_provider(provider_config, name=f"orchestrator_{provider_type}")
        logger.info(f"Using {provider_type.upper()} provider with model: {self.config.provider_model}")
        
        # Wrap online provider to match LLMClient interface
        return OnlineProviderWrapper(
            provider=provider,
            model=self.config.provider_model,
            temperature=self.config.temperature,
        )
    
    def _run_startup_recovery(self):
        """Run crash recovery on service startup."""
        logger.info("Running startup crash recovery scan...")
        
        try:
            crashed_threads = self.recovery_manager.scan_for_crashed_threads(
                older_than_minutes=5
            )
            
            if not crashed_threads:
                logger.info("No crashed threads found. Clean startup.")
                return
            
            logger.warning(f"Found {len(crashed_threads)} crashed threads. Attempting recovery...")
            
            recovered = 0
            failed = 0
            
            for thread_id in crashed_threads:
                try:
                    can_recover, reason = self.recovery_manager.can_recover_thread(thread_id)
                    if not can_recover:
                        logger.warning(f"Cannot recover thread {thread_id}: {reason}")
                        failed += 1
                        continue
                    
                    checkpoint_state = self.recovery_manager.load_checkpoint_state(thread_id)
                    if not checkpoint_state:
                        logger.error(f"Failed to load checkpoint for {thread_id}")
                        self.recovery_manager.mark_recovery_attempt(thread_id, success=False)
                        failed += 1
                        continue
                    
                    self.checkpoint_manager.mark_thread_complete(thread_id)
                    self.recovery_manager.mark_recovery_attempt(thread_id, success=True)
                    recovered += 1
                    
                    logger.info(f"Successfully recovered thread {thread_id}")
                    
                except Exception as e:
                    logger.error(f"Recovery failed for thread {thread_id}: {e}", exc_info=True)
                    self.recovery_manager.mark_recovery_attempt(thread_id, success=False)
                    failed += 1
            
            logger.info(f"Recovery complete: {recovered} recovered, {failed} failed")
            report = self.recovery_manager.get_recovery_report()
            logger.info(f"Recovery report: {report}")
            
        except Exception as e:
            logger.error(f"Startup recovery scan failed: {e}", exc_info=True)
    
    def _get_thread_id(self, context: grpc.ServicerContext) -> Optional[str]:
        """Extract thread-id from gRPC metadata if provided."""
        try:
            md = context.invocation_metadata()
            for item in md:
                key = (item[0] or "").lower()
                if key == "thread-id":
                    val = item[1]
                    if isinstance(val, bytes):
                        return val.decode("utf-8", errors="ignore")
                    if isinstance(val, str):
                        return val
        except Exception:
            pass
        return None
    
    def delegate_to_worker(self, task: str, capability: str) -> str:
        """
        Delegate a task to a specialized worker agent.
        
        Args:
            task (str): The instruction for the worker.
            capability (str): The required capability (e.g., 'coding', 'rag').
            
        Returns:
            str: The result from the worker.
        """
        logger.info(f"Delegating task '{task}' to worker with capability '{capability}'")
        
        # Discover workers
        agents = self.registry_client.discover(capability)
        if not agents:
            return f"Error: No workers found with capability '{capability}'"
        
        # Pick the first one (simple load balancing)
        worker_profile = agents[0]
        logger.info(f"Selected worker: {worker_profile.name} at {worker_profile.endpoint}")
        
        # Execute task
        worker_client = WorkerClient(worker_profile.endpoint)
        response = worker_client.execute_task(
            task_id=str(uuid.uuid4()),
            instruction=task
        )
        
        if response and response.status == "success":
            return response.result
        else:
            return f"Error executing task: {response.error_message if response else 'Unknown error'}"

    def QueryAgent(self, request, context):
        """
        Process user query through orchestrator.
        
        Executes appropriate agent workflow using LLM decision making.
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[{request_id}] Query: '{request.user_query}'")
        
        try:
            # Get or create thread_id
            thread_id = self._get_thread_id(context) or request_id
            
            # Mark thread as incomplete (for crash recovery)
            self.checkpoint_manager.mark_thread_incomplete(thread_id)
            
            # Process through agent workflow
            result = self._process_query(
                query=request.user_query,
                thread_id=thread_id
            )
            
            # Mark thread as complete
            self.checkpoint_manager.mark_thread_complete(thread_id)
            
            # Extract response
            content = result.get("content") or "Sorry, I couldn't generate a response."
            sources = self._build_sources_metadata(result, thread_id)
            
            elapsed = time.time() - start_time
            logger.info(f"[{request_id}] Completed in {elapsed:.2f}s")
            
            return agent_pb2.AgentReply(
                final_answer=content,
                context_used=json.dumps([]),
                sources=json.dumps(sources),
                execution_graph=""
            )
            
        except Exception as e:
            logger.exception(f"[{request_id}] Error: {e}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error. Request ID: {request_id}")
            return agent_pb2.AgentReply(
                final_answer=f"Sorry, an error occurred. (Request ID: {request_id})",
                sources=json.dumps({"error": str(e), "request_id": request_id})
            )
    
    def _process_query(
        self,
        query: str,
        thread_id: str
    ) -> Dict[str, Any]:
        """Process query through agent workflow."""
        # Create initial state with thread_id as conversation_id
        state = create_initial_state(
            conversation_id=thread_id,
            metadata={
                "query": query
            }
        )
        
        # Add user query as HumanMessage
        state["messages"] = [HumanMessage(content=query)]
        
        # Configure thread
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "orchestrator"
            }
        }
        
        # Invoke compiled workflow
        final_state = self.compiled_workflow.invoke(state, config=config)
        
        # Extract results
        messages = final_state.get("messages", [])
        last_message = messages[-1] if messages else None
        
        content = ""
        if last_message:
            if isinstance(last_message, AIMessage):
                content = last_message.content
            else:
                content = str(last_message.content)
        
        return {
            "content": content,
            "messages": messages,
            "tool_results": final_state.get("tool_results", []),
            "iteration": final_state.get("iteration", 0)
        }
    
    def _build_sources_metadata(self, result: Dict, thread_id: str) -> Dict:
        """Build sources metadata from result."""
        tool_results = result.get("tool_results", [])
        
        sources = {
            "thread_id": thread_id,
            "iterations": result.get("iteration", 0),
            "tools_used": []
        };
        
        for tr in tool_results:
            if isinstance(tr, dict):
                # Handle both ToolExecutionResult.to_dict() format (tool_name) and legacy format (tool)
                tool_name = tr.get("tool_name") or tr.get("tool", "unknown")
                status = tr.get("status", "unknown")
                sources["tools_used"].append({
                    "tool": tool_name,
                    "status": status
                })
        
        return sources


def serve(config: Optional[OrchestratorConfig] = None):
    """Start the orchestrator gRPC server."""
    config = config or OrchestratorConfig.from_env()
    
    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        options=[
            ('grpc.max_send_message_length', 50 * 1024 * 1024),
            ('grpc.max_receive_message_length', 50 * 1024 * 1024),
        ]
    )
    
    # Add orchestrator service
    orchestrator_service = OrchestratorService(config)
    agent_pb2_grpc.add_AgentServiceServicer_to_server(orchestrator_service, server)
    
    # Add health check
    health_servicer = health.HealthServicer()
    health_servicer.set("", health_pb2.HealthCheckResponse.SERVING)
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)
    
    # Add reflection
    SERVICE_NAMES = (
        agent_pb2.DESCRIPTOR.services_by_name['AgentService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)
    
    # Start server
    server.add_insecure_port(f'{config.host}:{config.port}')
    server.start()
    logger.info(f"Orchestrator server started on {config.host}:{config.port}")
    
    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down orchestrator server...")
        server.stop(grace=5)


if __name__ == '__main__':
    serve()
