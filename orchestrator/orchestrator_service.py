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
from .simple_router import SimpleRouter, Route

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

# Protobuf imports (will use agent.proto initially)
try:
    # When running as module
    from shared.generated import agent_pb2
    from shared.generated import agent_pb2_grpc
except ImportError:
    try:
        # When running in Docker
        from . import agent_pb2
        from . import agent_pb2_grpc
    except ImportError:
        # Fallback
        import agent_pb2
        import agent_pb2_grpc


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("orchestrator")


class LLMEngineWrapper:
    """Wrapper around LLM client to provide consistent interface."""
    
    def __init__(self, llm_client: LLMClient, temperature: float = 0.7, max_tokens: int = 512):
        self.client = llm_client
        self.temperature = temperature
        self.max_tokens = max_tokens
        logger.info(f"LLMEngineWrapper initialized: temp={temperature}, max_tokens={max_tokens}")
    
    def generate(self, messages: list, tools: list = None, temperature: float = None, 
                 max_tokens: int = None, stream: bool = False) -> dict:
        """
        Generate response from LLM.
        
        Args:
            messages: List of message dicts with 'role' and 'content'
            tools: Optional list of tool schemas
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            stream: Whether to stream response (not implemented)
        
        Returns:
            dict with 'content' and optionally 'tool_calls'
        """
        # Use provided values or defaults
        temp = temperature if temperature is not None else self.temperature
        max_tok = max_tokens if max_tokens is not None else self.max_tokens
        
        # Convert messages to prompt string (simple concatenation for now)
        prompt = ""
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt += f"System: {content}\n"
            elif role == "user":
                prompt += f"User: {content}\n"
            elif role == "assistant":
                prompt += f"Assistant: {content}\n"
        
        # For now, call LLMClient.generate() with simple prompt
        # TODO: Enhance to support structured message format and tool calls
        try:
            response_text = self.client.generate(
                prompt=prompt,
                max_tokens=max_tok,
                temperature=temp
            )
            
            return {
                "content": response_text,
                "tool_calls": []  # Tool calling not yet implemented in simple wrapper
            }
        except Exception as e:
            logger.error(f"LLM generation error: {e}")
            return {
                "content": "Sorry, I encountered an error generating a response.",
                "tool_calls": []
            }
    
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
    
    Responsibilities:
    - Route queries to appropriate tools/services using SimpleRouter
    - Execute agent workflows via AgentWorkflow
    - Manage conversation persistence with CheckpointManager
    - Handle crash recovery on startup
    """
    
    def __init__(self, config: Optional[OrchestratorConfig] = None):
        """Initialize orchestrator service."""
        self.config = config or OrchestratorConfig.from_env()
        logger.info(f"Initializing Orchestrator on {self.config.host}:{self.config.port}")
        
        # Initialize router (lightweight keyword-based)
        self.router = SimpleRouter()
        logger.info("SimpleRouter initialized (keyword-based routing)")
        
        # Initialize tool registry
        self.registry = LocalToolRegistry()
        self._register_tools()
        
        # Initialize checkpoint manager
        self.checkpoint_manager = CheckpointManager(self.config.checkpoint_db_path)
        self.checkpointer = self.checkpoint_manager.create_checkpointer()
        
        # Initialize LLM client and wrapper
        llm_client = LLMClient(host=self.config.llm_host, port=self.config.llm_port)
        self.llm_engine = LLMEngineWrapper(
            llm_client,
            temperature=self.config.temperature,
            max_tokens=512
        )
        
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
            tool_registry=self.registry,
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
    
    def _register_tools(self):
        """Register built-in tools with the registry."""
        self.registry.register(web_search)
        logger.info("Registered tool: web_search")
        
        self.registry.register(math_solver)
        logger.info("Registered tool: math_solver")
        
        self.registry.register(load_web_page)
        logger.info("Registered tool: load_web_page")
        
        logger.info(f"Total tools registered: {len(self.registry.get_available_tools())}")
    
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
    
    def QueryAgent(self, request, context):
        """
        Process user query through orchestrator.
        
        Uses SimpleRouter for lightweight intent classification,
        then executes appropriate agent workflow.
        """
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[{request_id}] Query: '{request.user_query}'")
        
        try:
            # Get or create thread_id
            thread_id = self._get_thread_id(context) or request_id
            
            # Route query using SimpleRouter
            route = self.router.route(request.user_query)
            logger.info(
                f"[{request_id}] Route: {route.service}/{route.tool or 'direct'} "
                f"(confidence={route.confidence:.2f})"
            )
            
            # Mark thread as incomplete (for crash recovery)
            self.checkpoint_manager.mark_thread_incomplete(thread_id)
            
            # Process through agent workflow
            result = self._process_query(
                query=request.user_query,
                thread_id=thread_id,
                route=route
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
        thread_id: str,
        route: Route
    ) -> Dict[str, Any]:
        """Process query through agent workflow."""
        # Create initial state
        state = create_initial_state(query)
        
        # Add routing hint if available
        if route.tool:
            state["routing_hint"] = route.tool
        
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
        }
        
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
