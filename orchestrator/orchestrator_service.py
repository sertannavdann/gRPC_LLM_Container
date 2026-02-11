"""
Orchestrator gRPC service - Unified agent coordination service.

Routes queries to appropriate tools/services, manages agent workflows,
handles conversation persistence, and provides crash recovery.
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

# Observability imports
from shared.observability import (
    setup_observability,
    shutdown_observability,
    create_request_metrics,
    create_tool_metrics,
    create_provider_metrics,
    create_lidm_metrics,
    create_decision_pipeline_metrics,
    create_span,
    get_correlation_id,
    set_correlation_id,
    increment_active_requests,
    decrement_active_requests,
    update_context_utilization,
    RequestMetrics,
    ToolMetrics,
    ProviderMetrics,
    LIDMMetrics,
    DecisionPipelineMetrics,
    MemoryReporter,
)
from shared.observability.grpc_interceptor import ObservabilityServerInterceptor

# Import configuration
from .config import OrchestratorConfig

# Import intent patterns for multi-tool guardrails
from .intent_patterns import (
    analyze_intent,
    detect_intent,
    get_intent_system_prompt,
    should_continue_tool_loop,
    resolve_destination,
    IntentAnalysis,
)

# Import shared JSON parser for robust tool response parsing
from shared.utils.json_parser import extract_tool_json, safe_parse_arguments

from shared.clients.llm_client import LLMClient, LLMClientPool
from core.checkpointing import CheckpointManager, RecoveryManager
from core import AgentWorkflow, WorkflowConfig
from core.state import create_initial_state
from core.self_consistency import SelfConsistencyVerifier
from tools.registry import LocalToolRegistry
from tools.builtin.web_search import web_search
from tools.builtin.math_solver import math_solver, set_sandbox_executor
from tools.builtin.web_loader import load_web_page
from tools.builtin.code_executor import execute_code, set_sandbox_client
from tools.builtin.user_context import get_user_context, get_daily_briefing, get_commute_time
from tools.builtin.knowledge_search import search_knowledge, store_knowledge
from tools.builtin.finance_query import query_finance
from tools.builtin.module_builder import build_module, write_module_code
from tools.builtin.module_validator import validate_module
from tools.builtin.module_validator import set_sandbox_client as set_validator_sandbox
from tools.builtin.module_manager import (
    list_modules, enable_module, disable_module, store_module_credentials,
    set_module_loader, set_module_registry, set_credential_store,
)
from shared.modules.registry import ModuleRegistry
from shared.modules.credentials import CredentialStore
from tools.builtin.module_installer import (
    install_module, uninstall_module, set_installer_deps,
)

# Module system for dynamic adapter loading
from shared.modules.loader import ModuleLoader

from langchain_core.messages import HumanMessage, AIMessage, ToolMessage

# Client imports
from shared.clients.sandbox_client import SandboxClient
from shared.clients.chroma_client import ChromaClient

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
from pathlib import Path
import asyncio
import threading

# LIDM imports
from .delegation_manager import DelegationManager
from .capability_map import get_lidm_endpoints, set_config_manager
from .config_manager import ConfigManager
from .routing_config import RoutingConfig

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
        provider_metrics: Optional[ProviderMetrics] = None,
        provider_name: str = "unknown",
    ):
        """
        Initialize the wrapper.

        Args:
            provider: Online provider instance (PerplexityProvider, OpenAIProvider, etc.)
            model: Model name to use for completions
            temperature: Default temperature setting
            provider_metrics: Optional metrics for tracking provider calls
            provider_name: Name of the provider for metrics labels
        """
        self.provider = provider
        self.model = model
        self.temperature = temperature
        self.provider_metrics = provider_metrics
        self.provider_name = provider_name
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
        start_time = time.time()

        # Build ChatRequest
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model=self.model,
            temperature=temp,
            max_tokens=max_tokens,
        )

        if response_format == "json":
            request.extra["response_format"] = {"type": "json_object"}

        try:
            # Run async generate
            response = self._run_async(self.provider.generate(request))

            # Record provider metrics
            if self.provider_metrics:
                duration_ms = (time.time() - start_time) * 1000
                self.provider_metrics.provider_requests_total.add(
                    1, {"provider": self.provider_name, "model": self.model, "status": "success"}
                )
                self.provider_metrics.provider_latency_ms.record(
                    duration_ms, {"provider": self.provider_name, "model": self.model}
                )

            return response.content

        except Exception as e:
            # Record error metrics
            if self.provider_metrics:
                self.provider_metrics.provider_errors_total.add(
                    1, {"provider": self.provider_name, "model": self.model, "error_type": type(e).__name__}
                )
            raise
    
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
        sandbox_client = None,  # Optional SandboxClient for code execution
        pipeline_metrics: Optional[DecisionPipelineMetrics] = None,
    ):
        self.client = llm_client
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_tool_iterations = max_tool_iterations
        self.sandbox_client = sandbox_client
        self.pipeline_metrics = pipeline_metrics
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
            infer_start = time.perf_counter()
            response_text = self.client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature
            )
            infer_ms = (time.perf_counter() - infer_start) * 1000

            # Record inference metrics
            if self.pipeline_metrics:
                self.pipeline_metrics.inference_duration_ms.record(
                    infer_ms, {"mode": "direct"})
                # Approximate token count (~4 chars/token) and record rate
                approx_tokens = max(len(response_text) // 4, 1)
                if infer_ms > 0:
                    tps = approx_tokens / (infer_ms / 1000)
                    self.pipeline_metrics.token_generation_rate.record(
                        tps, {"mode": "direct"})

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

        # If we have tool results, use plain-text synthesis instead of JSON
        # This is far more reliable across model sizes
        if has_tool_results:
            return self._synthesize_with_results(messages, conversation, temperature, max_tokens)

        # Track multi-turn context
        rollout_context = conversation
        tool_calls_made = []
        iteration = 0

        while iteration < self.max_tool_iterations:
            iteration += 1

            # First call: determine if tools are needed (synthesis handled by _synthesize_with_results)
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
                infer_start = time.perf_counter()
                response_text = self.client.generate(
                    prompt=prompt,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    response_format="json"
                )
                infer_ms = (time.perf_counter() - infer_start) * 1000
                if self.pipeline_metrics:
                    self.pipeline_metrics.inference_duration_ms.record(
                        infer_ms, {"mode": "tool_calling"})

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
    
    def _synthesize_with_results(self, messages: list, conversation: str, temperature: float, max_tokens: int) -> dict:
        """
        Synthesize a final answer from tool results using plain-text output.

        Instead of forcing JSON output (which small models struggle with),
        this method asks the LLM to produce a natural language answer
        directly from the tool results.
        """
        # Extract the original user query
        original_query = ""
        for msg in messages:
            if isinstance(msg, HumanMessage):
                original_query = msg.content
                break

        # Extract tool results from ToolMessages
        tool_results_text = []
        for msg in messages:
            if isinstance(msg, ToolMessage):
                tool_results_text.append(f"[{msg.name}]: {msg.content}")

        results_block = "\n".join(tool_results_text) if tool_results_text else "No tool results available."

        prompt = f"""You are a helpful AI assistant. The user asked a question and tools were used to gather information.

User's question: {original_query}

Tool results:
{results_block}

Using the tool results above, provide a clear, complete, and helpful answer to the user's question.
Be direct and specific — include relevant numbers, times, and details from the tool results.
Do NOT mention that tools were used. Just answer naturally.

Answer:"""

        logger.debug(f"Synthesis prompt length={len(prompt)}")

        try:
            infer_start = time.perf_counter()
            response_text = self.client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                # No response_format="json" — plain text output
            )
            infer_ms = (time.perf_counter() - infer_start) * 1000
            if self.pipeline_metrics:
                self.pipeline_metrics.inference_duration_ms.record(
                    infer_ms, {"mode": "synthesis"})
                approx_tokens = max(len(response_text) // 4, 1)
                if infer_ms > 0:
                    tps = approx_tokens / (infer_ms / 1000)
                    self.pipeline_metrics.token_generation_rate.record(
                        tps, {"mode": "synthesis"})

            content = response_text.strip()
            logger.info(f"Tool result synthesis complete: {len(content)} chars")

            return {
                "content": content,
                "tool_calls": [],
                "_synthesis_metadata": {
                    "tool_results_count": len(tool_results_text),
                    "original_query": original_query[:100],
                }
            }
        except Exception as e:
            logger.error(f"Synthesis generation error: {e}")
            # Fallback: return raw tool results
            return {
                "content": f"Here are the results I found:\n{results_block}",
                "tool_calls": []
            }

    def _parse_tool_response(self, response_text: str) -> dict:
        """Parse LLM's JSON response into content or tool_calls.
        
        Uses shared/utils/json_parser.py for robust extraction.
        """
        try:
            # Clean response text
            response_text = response_text.strip()
            logger.debug(f"Raw LLM response length={len(response_text)}, first 500 chars: {response_text[:500] if response_text else '(empty)'}")
            
            # Use shared JSON parser for robust extraction
            parsed = extract_tool_json(response_text)
            
            if parsed is None:
                # No valid JSON found - treat as direct answer
                logger.warning(f"No valid JSON in response, treating as direct answer: {response_text[:200]}...")
                return {
                    "content": response_text,
                    "tool_calls": [],
                    "_parse_note": "No valid JSON found, returned raw text"
                }
            
            response_type = parsed.get("type", "answer")
            
            if response_type == "tool_call":
                # Extract tool call
                tool_name = parsed.get("tool", "")
                tool_args = safe_parse_arguments(parsed.get("arguments", {}))
                
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

        # Initialize observability if enabled
        self.observability_enabled = os.getenv("ENABLE_OBSERVABILITY", "false").lower() == "true"
        self.request_metrics: Optional[RequestMetrics] = None
        self.tool_metrics: Optional[ToolMetrics] = None
        self.provider_metrics: Optional[ProviderMetrics] = None
        self.lidm_metrics: Optional[LIDMMetrics] = None
        self.pipeline_metrics: Optional[DecisionPipelineMetrics] = None
        self._memory_reporter: Optional[MemoryReporter] = None

        if self.observability_enabled:
            logger.info("Initializing observability stack...")
            setup_observability(
                service_name="orchestrator",
                service_version="1.0.0",
                enable_prometheus=True,
            )
            # Create metrics instances
            self.request_metrics = create_request_metrics()
            self.tool_metrics = create_tool_metrics()
            self.provider_metrics = create_provider_metrics()
            self.lidm_metrics = create_lidm_metrics()
            self.pipeline_metrics = create_decision_pipeline_metrics()

            # Start background memory reporter (snapshots RSS every 15s)
            self._memory_reporter = MemoryReporter(interval_seconds=15.0)
            self._memory_reporter.start()
            logger.info("Observability initialized with metrics (incl. LIDM + pipeline + memory)")
        else:
            logger.info("Observability disabled (set ENABLE_OBSERVABILITY=true to enable)")

        # Initialize dynamic routing config
        config_path = os.getenv("ROUTING_CONFIG_PATH", "/app/config/routing_config.json")
        self.config_manager = ConfigManager(config_path)
        set_config_manager(self.config_manager)

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
        
        # NOTE: Registry/Worker mesh disabled - can be re-enabled when needed
        # Registry and Worker services removed in cleanup

        # Initialize ChromaDB client for context compaction archival
        try:
            self.chroma_client = ChromaClient()
            logger.info(f"ChromaDB client connected for context archival")
        except Exception as e:
            logger.warning(f"ChromaDB client init failed: {e}. Context archival disabled.")
            self.chroma_client = None

        # Initialize Self-Consistency Verifier (Agent0 Phase 2)
        self.self_consistency_verifier = None
        if self.config.enable_self_consistency:
            self.self_consistency_verifier = SelfConsistencyVerifier(
                llm_client=self.llm_client,
                num_samples=self.config.self_consistency_samples,
                consistency_threshold=self.config.self_consistency_threshold
            )
            logger.info(f"Self-consistency enabled: k={self.config.self_consistency_samples}, threshold={self.config.self_consistency_threshold}")
        
        # LIDM: Initialize delegation manager if enabled
        self.delegation_enabled = os.getenv("ENABLE_DELEGATION", "false").lower() == "true"
        self.delegation_manager = None
        self.llm_pool = None

        if self.delegation_enabled:
            routing_config = self.config_manager.get_config()
            endpoints = routing_config.get_tier_endpoints() or get_lidm_endpoints()
            # Guard: verify at least one non-heavy endpoint is reachable
            reachable = self._check_lidm_endpoints(endpoints)
            if reachable:
                self.llm_pool = LLMClientPool(reachable)
                self.delegation_manager = DelegationManager(
                    self.llm_pool,
                    metrics=self.lidm_metrics,
                    config=routing_config,
                )
                # Register observers for hot-reload
                self.config_manager.register_observer(self.delegation_manager.on_config_changed)
                self.config_manager.register_observer(self._on_routing_config_changed)
                logger.info(f"LIDM delegation enabled with tiers: {self.llm_pool.available_tiers}")
            else:
                self.delegation_enabled = False
                logger.warning("LIDM delegation requested but no tier endpoints reachable — disabled")
        else:
            logger.info("LIDM delegation disabled (set ENABLE_DELEGATION=true to enable)")

        # Initialize LLM Engine Wrapper with multi-turn support
        self.llm_engine = LLMEngineWrapper(
            self.llm_client,
            temperature=self.config.temperature,
            max_tokens=512,
            max_tool_iterations=self.config.max_iterations,
            sandbox_client=self.sandbox_client,
            pipeline_metrics=self.pipeline_metrics,
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

        # Register knowledge base (RAG) tools
        self.tool_registry.register(search_knowledge)
        self.tool_registry.register(store_knowledge)

        # Register code executor if sandbox is available
        if self.sandbox_client:
            self.tool_registry.register(execute_code)
            # Wire sandbox into math_solver for codegen→sandbox pipeline
            set_sandbox_executor(execute_code)
            logger.info("Code executor tool registered + math_solver sandbox wired")

        # Register finance query tool (bank transaction access)
        self.tool_registry.register(query_finance)

        # Register module building tools (NEXUS self-evolution)
        self.tool_registry.register(build_module)
        self.tool_registry.register(write_module_code)
        self.tool_registry.register(validate_module)
        if self.sandbox_client:
            set_validator_sandbox(self.sandbox_client)

        # Register module management tools
        self.tool_registry.register(list_modules)
        self.tool_registry.register(enable_module)
        self.tool_registry.register(disable_module)
        self.tool_registry.register(store_module_credentials)

        # Register module installer tools
        self.tool_registry.register(install_module)
        self.tool_registry.register(uninstall_module)
        set_installer_deps(self.module_loader, self.module_registry, self.credential_store)

        # NOTE: delegate_to_worker removed - worker mesh disabled

        # Dynamic module loading from modules/ directory
        modules_dir = Path(os.getenv("MODULES_DIR", "/app/modules"))
        self.module_loader = ModuleLoader(modules_dir)
        self.module_registry = ModuleRegistry(
            db_path=os.getenv("MODULE_REGISTRY_DB", "data/module_registry.db")
        )
        self.credential_store = CredentialStore(
            db_path=os.getenv("MODULE_CREDENTIALS_DB", "data/module_credentials.db")
        )

        # Wire module infrastructure into manager tools
        set_module_loader(self.module_loader)
        set_module_registry(self.module_registry)
        set_credential_store(self.credential_store)

        try:
            loaded = self.module_loader.load_all_modules()
            loaded_count = sum(1 for h in loaded if h.is_loaded)
            if loaded_count > 0:
                logger.info(f"Dynamic modules loaded: {loaded_count}")
                # Record installed modules in persistent registry
                for h in loaded:
                    if h.is_loaded:
                        self.module_registry.install(h.manifest)
        except Exception as e:
            logger.warning(f"Module loader initialization failed: {e}")

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
            config=self.workflow_config,
            chroma_client=self.chroma_client,
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
            # Record provider initialization metric
            if self.observability_enabled and self.provider_metrics:
                self.provider_metrics.provider_requests_total.add(
                    1, {"provider": "local", "operation": "init"}
                )
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

        # Record provider initialization metric
        if self.observability_enabled and self.provider_metrics:
            self.provider_metrics.provider_requests_total.add(
                1, {"provider": provider_type, "operation": "init"}
            )

        # Wrap online provider to match LLMClient interface
        return OnlineProviderWrapper(
            provider=provider,
            model=self.config.provider_model,
            temperature=self.config.temperature,
            provider_metrics=self.provider_metrics if self.observability_enabled else None,
            provider_name=provider_type,
        )

    def _on_routing_config_changed(self, config: RoutingConfig) -> None:
        """Observer callback: reconfigure LLMClientPool tier endpoints on hot-reload."""
        if self.llm_pool is None:
            return
        new_endpoints = config.get_tier_endpoints()
        if new_endpoints:
            self.llm_pool.reconfigure(new_endpoints)
            logger.info(f"LLMClientPool reconfigured: tiers={self.llm_pool.available_tiers}")

    @staticmethod
    def _check_lidm_endpoints(endpoints: Dict[str, str]) -> Dict[str, str]:
        """
        Probe LIDM tier endpoints and return only reachable ones.

        Uses a fast TCP connect (1s timeout) so the orchestrator never blocks
        on a missing llm_service_standard container.
        """
        import socket

        reachable: Dict[str, str] = {}
        for tier, addr in endpoints.items():
            if not addr:
                continue
            try:
                host, port_str = addr.rsplit(":", 1)
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1.0)
                result = sock.connect_ex((host, int(port_str)))
                sock.close()
                if result == 0:
                    reachable[tier] = addr
                    logger.info(f"LIDM tier '{tier}' reachable at {addr}")
                else:
                    logger.warning(f"LIDM tier '{tier}' at {addr} — not reachable (skipped)")
            except Exception as e:
                logger.warning(f"LIDM tier '{tier}' at {addr} — probe error: {e} (skipped)")
        return reachable
    
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
    
    # NOTE: Worker delegation disabled - services removed in cleanup
    # Uncomment and restore registry_client/worker_client if worker mesh is needed
    # def delegate_to_worker(self, task: str, capability: str) -> str:
    #     """Delegate a task to a specialized worker agent."""
    #     ...

    def QueryAgent(self, request, context):
        """
        Process user query through orchestrator.

        Executes appropriate agent workflow using LLM decision making.
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[{request_id}] Query: '{request.user_query}'")

        # Set correlation ID for tracing
        if self.observability_enabled:
            set_correlation_id(request_id)
            increment_active_requests()

        try:
            # Get or create thread_id
            thread_id = self._get_thread_id(context) or request_id

            # Record request metric
            if self.observability_enabled and self.request_metrics:
                self.request_metrics.requests_total.add(
                    1, {"method": "QueryAgent", "type": "unary"}
                )

            # Mark thread as incomplete (for crash recovery)
            self.checkpoint_manager.mark_thread_incomplete(thread_id)

            # Process through agent workflow with tracing
            if self.observability_enabled:
                with create_span(
                    name="QueryAgent.process",
                    attributes={
                        "request_id": request_id,
                        "thread_id": thread_id,
                        "query_length": len(request.user_query),
                    }
                ):
                    result = self._process_query(
                        query=request.user_query,
                        thread_id=thread_id
                    )
            else:
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

            # Record request duration metric
            if self.observability_enabled and self.request_metrics:
                self.request_metrics.request_duration_ms.record(
                    elapsed * 1000, {"method": "QueryAgent", "status": "ok"}
                )
                # Record tools per request
                if self.tool_metrics:
                    tools_used = len(sources.get("tools_used", []))
                    self.tool_metrics.tools_per_request.record(
                        tools_used, {"method": "QueryAgent"}
                    )

            return agent_pb2.AgentReply(
                final_answer=content,
                context_used=json.dumps([]),
                sources=json.dumps(sources),
                execution_graph=""
            )

        except Exception as e:
            logger.exception(f"[{request_id}] Error: {e}")

            # Record error metrics
            if self.observability_enabled and self.request_metrics:
                elapsed = time.time() - start_time
                self.request_metrics.errors_total.add(
                    1, {"method": "QueryAgent", "error_type": type(e).__name__}
                )
                self.request_metrics.request_duration_ms.record(
                    elapsed * 1000, {"method": "QueryAgent", "status": "error"}
                )

            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error. Request ID: {request_id}")
            return agent_pb2.AgentReply(
                final_answer=f"Sorry, an error occurred. (Request ID: {request_id})",
                sources=json.dumps({"error": str(e), "request_id": request_id})
            )

        finally:
            # Decrement active requests
            if self.observability_enabled:
                decrement_active_requests()
    
    def _process_query(
        self,
        query: str,
        thread_id: str
    ) -> Dict[str, Any]:
        """Process query through agent workflow with intent-based guardrails."""
        
        # Analyze intent for multi-tool queries
        intent_analysis = analyze_intent(query)

        # Record classification metric
        if self.observability_enabled and self.pipeline_metrics:
            intent_name = intent_analysis.intent.name if intent_analysis.intent else "general"
            self.pipeline_metrics.classification_total.add(
                1, {"category": intent_name, "tier": "standard"})

        # Check if clarification is needed (e.g., missing destination)
        if intent_analysis.needs_clarification:
            logger.info(f"Intent requires clarification: {intent_analysis.clarifying_question}")
            return {
                "content": intent_analysis.clarifying_question,
                "messages": [],
                "tool_results": [],
                "iteration": 0,
                "needs_clarification": True
            }
        
        # LIDM: If delegation is enabled, try routing through DelegationManager
        if self.delegation_enabled and self.delegation_manager:
            lidm_start = time.perf_counter()
            try:
                decomposition = self.delegation_manager.analyze_and_route(query)
                strategy = decomposition.strategy
                logger.info(f"LIDM strategy={strategy}, "
                             f"sub_tasks={len(decomposition.sub_tasks)}, "
                             f"complexity={decomposition.complexity_score:.2f}")

                # Record LIDM classification
                if self.observability_enabled and self.pipeline_metrics:
                    task_type = decomposition.task_type if hasattr(decomposition, "task_type") else "unknown"
                    for st in decomposition.sub_tasks:
                        self.pipeline_metrics.classification_total.add(
                            1, {"category": task_type, "tier": st.target_tier})

                if strategy == "decompose" and len(decomposition.sub_tasks) > 1:
                    # Multi-task delegation
                    exec_result = self.delegation_manager.execute_delegation(decomposition)
                    content = self.delegation_manager.aggregate_results(
                        query, exec_result.get("completed", {}), decomposition
                    )

                    # Optional verification for high-complexity results
                    if decomposition.complexity_score > 0.8:
                        verification = self.delegation_manager.verify_result(
                            query, content, decomposition.complexity_score
                        )
                        if verification.get("revised_answer"):
                            content = verification["revised_answer"]
                        logger.info(f"LIDM verification: method={verification.get('method')}, "
                                     f"confidence={verification.get('confidence', 0):.2f}")

                    # Record LIDM metrics
                    if self.observability_enabled and self.lidm_metrics:
                        elapsed = (time.perf_counter() - lidm_start) * 1000
                        self.lidm_metrics.delegation_requests_total.add(
                            1, {"strategy": "decompose", "tier": "multi"})
                        self.lidm_metrics.delegation_latency_ms.record(
                            elapsed, {"strategy": "decompose", "tier": "multi"})

                    return {
                        "content": content,
                        "messages": [],
                        "tool_results": exec_result.get("sub_results", []),
                        "iteration": 0,
                        "lidm_strategy": strategy,
                    }

                elif strategy == "direct" and decomposition.sub_tasks:
                    # Single capability, route to best tier
                    task = decomposition.sub_tasks[0]
                    tier = task.target_tier

                    # If routing to a non-default tier, use the pool directly
                    if tier != "heavy" or self.llm_pool:
                        result = self.llm_pool.generate(
                            prompt=query, tier=tier, max_tokens=1024
                        )

                        # Record LIDM metrics
                        if self.observability_enabled and self.lidm_metrics:
                            elapsed = (time.perf_counter() - lidm_start) * 1000
                            self.lidm_metrics.delegation_requests_total.add(
                                1, {"strategy": "direct", "tier": tier})
                            self.lidm_metrics.delegation_latency_ms.record(
                                elapsed, {"strategy": "direct", "tier": tier})

                        return {
                            "content": result,
                            "messages": [],
                            "tool_results": [],
                            "iteration": 0,
                            "lidm_strategy": "direct",
                            "lidm_tier": tier,
                        }
                    # Fall through to standard workflow for heavy tier (default)

            except Exception as e:
                logger.warning(f"LIDM delegation failed, falling back to standard workflow: {e}")
                if self.observability_enabled and self.lidm_metrics:
                    self.lidm_metrics.delegation_errors_total.add(
                        1, {"error": type(e).__name__})

        # Get system prompt enhancement for multi-tool intents
        intent_prompt = get_intent_system_prompt(query)
        
        # Create initial state with thread_id as conversation_id
        state = create_initial_state(
            conversation_id=thread_id,
            metadata={
                "query": query,
                "intent": intent_analysis.intent.name if intent_analysis.intent else None,
                "destination": intent_analysis.destination,
            }
        )

        # Add user query as HumanMessage, prepend intent guidance if applicable
        if intent_prompt:
            # Inject intent guidance into the conversation
            state["messages"] = [
                HumanMessage(content=f"[System Note: {intent_prompt}]\n\nUser: {query}")
            ]
            logger.debug(f"Injected intent prompt for '{intent_analysis.intent.name}'")
        else:
            state["messages"] = [HumanMessage(content=query)]

        # Configure thread
        config = {
            "configurable": {
                "thread_id": thread_id,
                "checkpoint_ns": "orchestrator"
            }
        }

        # Invoke compiled workflow with tracing
        if self.observability_enabled:
            with create_span(
                name="workflow.invoke",
                attributes={
                    "thread_id": thread_id,
                    "query_length": len(query),
                }
            ):
                final_state = self.compiled_workflow.invoke(state, config=config)
        else:
            final_state = self.compiled_workflow.invoke(state, config=config)

        # Extract results
        messages = final_state.get("messages", [])
        last_message = messages[-1] if messages else None

        # Update context window utilization gauge
        if self.observability_enabled and self.pipeline_metrics:
            total_chars = sum(len(str(m.content)) for m in messages if hasattr(m, "content"))
            # Approximate context usage: ~4 chars/token, config context_window is in K tokens
            max_tokens = self.config.context_window * 1024
            approx_tokens_used = total_chars // 4
            update_context_utilization(approx_tokens_used / max(max_tokens, 1))

        content = ""
        if last_message:
            if isinstance(last_message, AIMessage):
                content = last_message.content
            else:
                content = str(last_message.content)

        # Record tool metrics
        tool_results = final_state.get("tool_results", [])
        if self.observability_enabled and self.tool_metrics and tool_results:
            for tr in tool_results:
                if isinstance(tr, dict):
                    tool_name = tr.get("tool_name") or tr.get("tool", "unknown")
                    status = tr.get("status", "unknown")
                    duration = tr.get("duration_ms", 0)

                    # Record tool call
                    self.tool_metrics.tool_calls_total.add(
                        1, {"tool": tool_name, "status": status}
                    )

                    # Record tool duration if available
                    if duration > 0:
                        self.tool_metrics.tool_duration_ms.record(
                            duration, {"tool": tool_name}
                        )

                    # Record tool errors
                    if status == "error":
                        self.tool_metrics.tool_errors_total.add(
                            1, {"tool": tool_name}
                        )

        return {
            "content": content,
            "messages": messages,
            "tool_results": tool_results,
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

    # Check if observability is enabled
    observability_enabled = os.getenv("ENABLE_OBSERVABILITY", "false").lower() == "true"

    # Build interceptors list
    interceptors = []
    if observability_enabled:
        interceptors.append(ObservabilityServerInterceptor())
        logger.info("Observability server interceptor enabled")

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=10),
        interceptors=interceptors,
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

    # Start admin API for dynamic routing config (daemon thread)
    from .admin_api import start_admin_server
    admin_port = int(os.getenv("ADMIN_API_PORT", "8003"))
    start_admin_server(orchestrator_service.config_manager, port=admin_port)

    try:
        server.wait_for_termination()
    except KeyboardInterrupt:
        logger.info("Shutting down orchestrator server...")
        server.stop(grace=5)

        # Shutdown observability gracefully
        if observability_enabled:
            logger.info("Shutting down observability stack...")
            shutdown_observability()


if __name__ == '__main__':
    serve()
