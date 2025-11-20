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
from tools.registry import LocalToolRegistry
from tools.builtin.web_search import web_search
from tools.builtin.math_solver import math_solver  
from tools.builtin.web_loader import load_web_page

from langchain_core.messages import HumanMessage, AIMessage

# New imports for Registry and Worker clients
from shared.clients.registry_client import RegistryClient
from shared.clients.worker_client import WorkerClient
import os

# Protobuf imports
from shared.generated import agent_pb2
from shared.generated import agent_pb2_grpc


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestrator")


class LLMEngineWrapper:
    """Wrapper around LLM client with structured tool calling support."""
    
    def __init__(self, llm_client: LLMClient, temperature: float = 0.7, max_tokens: int = 512):
        self.client = llm_client
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info(f"LLMEngineWrapper initialized with tool calling support: temp={temperature}, max_tokens={max_tokens}")
    
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
        logger.info(f"LLMEngineWrapper.generate() called with {len(messages)} messages, {len(tools) if tools else 0} tools")
        
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
        """Generate response with tool calling capability using structured prompting."""
        
        # Format tools for prompt
        tools_desc = self._format_tools_description(tools)
        
        # Build conversation history including tool results
        conversation = self._format_messages_with_tools(messages)
        
        # Construct prompt with tool instructions
        prompt = f"""You are a helpful AI assistant with access to tools.

Available tools:
{tools_desc}

Instructions:
- To use a tool, respond with ONLY valid JSON in this exact format: {{"type": "tool_call", "tool": "tool_name", "arguments": {{"arg1": "value"}}}}
- To answer directly without tools, respond with ONLY valid JSON: {{"type": "answer", "content": "your answer here"}}
- IMPORTANT: Respond with ONLY the JSON object, no additional text before or after
- Choose the appropriate tool based on the user's question
- If no tool is needed, provide a direct answer

Conversation:
{conversation}

Your response (JSON only):"""

        logger.debug(f"Tool-enabled prompt generated ({len(prompt)} chars)")
        
        try:
            # Generate with JSON grammar constraint
            response_text = self.client.generate(
                prompt=prompt,
                max_tokens=max_tokens,
                temperature=temperature,
                response_format="json"  # Triggers JSON grammar in llm_service
            )
            
            # Parse response
            return self._parse_tool_response(response_text)
            
        except Exception as e:
            logger.error(f"Tool generation error: {e}", exc_info=True)
            return {
                "content": "I encountered an error while processing your request with tools.",
                "tool_calls": []
            }
    
    def _parse_tool_response(self, response_text: str) -> dict:
        """Parse LLM's JSON response into content or tool_calls."""
        try:
            # Clean response text
            response_text = response_text.strip()
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
    """
    
    def __init__(self, config: OrchestratorConfig = None):
        self.config = config or OrchestratorConfig.from_env()
        logger.info("Initializing Orchestrator on 0.0.0.0:50054")
        
        # Initialize clients
        self.llm_client = LLMClient(host=self.config.llm_host, port=self.config.llm_port)
        
        # Initialize Registry Client
        registry_host = os.getenv("REGISTRY_HOST", "registry_service")
        registry_port = int(os.getenv("REGISTRY_PORT", "50055"))
        self.registry_client = RegistryClient(host=registry_host, port=registry_port)
        
        # Initialize LLM Engine Wrapper
        self.llm_engine = LLMEngineWrapper(
            self.llm_client, 
            temperature=self.config.temperature,
            max_tokens=512
        )
        
        # Initialize Tool Registry
        self.tool_registry = LocalToolRegistry()
        
        # Register built-in tools
        self.tool_registry.register(web_search)
        self.tool_registry.register(math_solver)
        self.tool_registry.register(load_web_page)
        
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
                tool_name = tr.get("tool", "unknown")
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
