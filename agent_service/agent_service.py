# agent_service.py
import uuid
import grpc
import json
import logging
import time

import sqlite3
import atexit
from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from concurrent import futures
from grpc_reflection.v1alpha import reflection
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, FunctionMessage, SystemMessage
from pydantic import BaseModel, ValidationError
from collections import defaultdict

# Protobuf imports
from . import agent_pb2
from . import agent_pb2_grpc
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

# Local imports
from shared.clients.llm_client import LLMClient
from shared.clients.cpp_llm_client import CppLLMClient
from shared.clients.chroma_client import ChromaClient
# NOTE: ToolClient deprecated - will be replaced with function tools in Phase 2
# from shared.clients.tool_client import ToolClient
import os
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent_service")

# --------------------------
# Data Models
# --------------------------
class ToolConfig(BaseModel):
    name: str
    description: str
    circuit_breaker: bool = False
    failure_count: int = 0

class AgentMetrics(BaseModel):
    tool_usage: Dict[str, int] = defaultdict(int)
    tool_errors: Dict[str, int] = defaultdict(int)
    llm_calls: int = 0
    avg_response_time: float = 0.0

class AgentState(TypedDict):
    messages: List[HumanMessage | AIMessage | FunctionMessage | SystemMessage]
    context: List[dict]
    tools_used: List[str]
    errors: List[str]
    start_time: float

class WorkflowConfig(BaseModel):
    max_retries: int = 3
    context_window: int = 3
    error_window: int = 2

# --------------------------
# Core Components
# --------------------------
class ToolRegistry:
    """
    Legacy tool registry.
    
    .. deprecated:: Phase 1B
        This class is DEPRECATED and will be removed in Phase 2.
        Use ``tools.registry.LocalToolRegistry`` instead.
        
        Migration:
            OLD: registry = ToolRegistry()
            NEW: from tools.registry import registry (singleton instance)
    """
    def __init__(self):
        logger.warning("ToolRegistry is deprecated. Use tools.registry.LocalToolRegistry instead.")
        self.tools: Dict[str, callable] = {}
        self.configs: Dict[str, ToolConfig] = {}
    
    def register(self, name: str, func: callable, description: str):
        self.tools[name] = func
        self.configs[name] = ToolConfig(
            name=name,
            description=description
        )
    
    def get_tool(self, name: str) -> Optional[callable]:
        config = self.configs.get(name)
        if config and not config.circuit_breaker:
            return self.tools.get(name)
        return None
    
    def record_failure(self, name: str):
        if name in self.configs:
            self.configs[name].failure_count += 1
            if self.configs[name].failure_count >= 3:
                self.configs[name].circuit_breaker = True

    def get_available_tools(self) -> List[str]:
        return [name for name, config in self.configs.items() if not config.circuit_breaker]

    def reset_circuit_breaker(self, tool_name: str):
        if tool_name in self.configs:
            self.configs[tool_name].circuit_breaker = False
            self.configs[tool_name].failure_count = 0

class WorkflowBuilder:
    """
    Legacy workflow builder.
    
    .. deprecated:: Phase 1B
        This class is DEPRECATED and will be removed in Phase 2.
        Use ``core.graph.AgentWorkflow`` instead.
        
        Migration:
            OLD: builder = WorkflowBuilder(memory)
                 workflow = builder.build(agent_node, tool_node)
            NEW: from core.graph import AgentWorkflow
                 workflow = AgentWorkflow.create(registry, llm_engine, config, checkpointer)
    """
# Orchestrates the sequential execution steps of an agent system, 
# Determining when to use tools and when to terminate processing
    def __init__(self, memory: SqliteSaver):
        logger.warning("WorkflowBuilder is deprecated. Use core.graph.AgentWorkflow instead.")
        self.graph = StateGraph(AgentState)
        self.memory = memory
    
    def build(self, agent_node: callable, tool_node: callable) -> StateGraph:
        self.graph.add_node("agent", agent_node)
        self.graph.add_node("tool", tool_node)
        
        self.graph.set_entry_point("agent")
        self.graph.add_conditional_edges(
            "agent",
            self._should_continue,
            {"tool": "tool", END: END}
        )
        self.graph.add_edge("tool", "agent")
        
        return self.graph.compile(checkpointer=self.memory)

    @staticmethod
    def _should_continue(state: AgentState) -> str:
        last_msg = state["messages"][-1]
        if isinstance(last_msg, AIMessage) and last_msg.additional_kwargs.get("function_call"):
            return "tool"
        return END

class ResponseValidator:
    """
    Legacy response validator.
    
    .. deprecated:: Phase 1B
        This class is DEPRECATED and will be removed in Phase 2.
        Validation logic is now built into ``core.graph._validate_node()``.
    """
    def process_response(self, response: str, state: AgentState) -> Dict:
        logger.warning("ResponseValidator is deprecated. Validation is built into core.graph.")
        return self._process_response_impl(response, state)
    
    def _process_response_impl(self, response: str, state: AgentState) -> Dict:
        try:
            parsed = json.loads(response) if isinstance(response, str) else response
            # Centralized check for tool/function calls:
            tool_call = parsed.get("function_call") or parsed.get("tool_call")
            if tool_call:
                state["pending_tool"] = {
                    "name": tool_call.get("name"),
                    "arguments": tool_call.get("arguments")
                }
                return {
                    "messages": [AIMessage(content="", additional_kwargs={"function_call": tool_call})],
                    "pending_tool": state["pending_tool"],
                }
            content = parsed.get("content", parsed)
            if isinstance(content, dict):
                content = json.dumps(content)
            state.pop("pending_tool", None)
            return {"messages": [AIMessage(content=content)]}
        except (ValueError, ValidationError) as e:
            error_msg = f"LLM Error: {str(e)}"
            state.setdefault("errors", []).append(error_msg)
            return {"messages": [AIMessage(content=error_msg)]}


# --------------------------
# LLM Orchestrator
# --------------------------
class LLMOrchestrator:
    # Define a concrete system prompt template
    SYSTEM_PROMPT = \
"""You are a helpful assistant designed to answer user queries accurately and concisely.
You have access to the following tools:
{tool_descriptions}

Conversation History:
{history}

Context relevant to the query:
{context}

Recent Errors (if any):
{errors}

Current Request Timestamp: {timestamp}

Based on the history, context, errors, and the user's latest query, decide the next step.
1. If you can answer the query directly using the history and context, provide the final answer in JSON format: {{"content": "Your answer here."}}
2. If you need to use a tool, respond with a JSON object specifying the tool call: {{"function_call": {{"name": "tool_name", "arguments": {{"arg1": "value1", ...}}}}}}
   - Available tools: {tool_names}
   - Only use the tools listed. Ensure arguments are correctly formatted.
3. If the query is unclear or you cannot proceed, explain the issue: {{"content": "Explanation here."}}

User Query: {query}
Your JSON Response:"""

    def __init__(self, llm_client: LLMClient, config: WorkflowConfig, tool_registry: ToolRegistry):
        self.llm = llm_client
        self.validator = ResponseValidator()
        self.config = config # Store config
        self.tool_registry = tool_registry # Store tool registry

    def generate_response(self, state: AgentState) -> Dict:
        # Pass necessary info to _build_prompt
        prompt = self._build_prompt(state)
        self.metrics.llm_calls += 1 # Increment LLM calls metric

        # Assume llm.generate returns a string which might be JSON
        raw_response = self.llm.generate(
            prompt,
            max_tokens=1024, # Example: Adjust as needed
            temperature=0.5, # Example: Adjust as needed
            # Request JSON format from the LLM service if supported by your model/service
            # response_format="json" # Uncomment if llm_service supports this param
        )
        # Validate and structure the response
        return self.validator.process_response(raw_response, state)

    def _build_prompt(self, state: AgentState) -> str:
        """Enhanced prompt construction with dynamic context handling"""
        # Get available tools that are not circuit-broken
        available_tools = self.tool_registry.get_available_tools()
        tool_descriptions = "\n".join(
            f"- {name}: {self.tool_registry.configs[name].description}"
            for name in available_tools
        ) if available_tools else "No tools available."

        context_items = state.get("context", [])[-self.config.context_window:]
        error_items = state.get("errors", [])[-self.config.error_window:]

        # Format history using the helper function
        history_str = format_messages_to_prompt(state["messages"][:-1]) # Exclude the latest query

        return self.SYSTEM_PROMPT.format(
            tool_descriptions=tool_descriptions,
            tool_names=", ".join(available_tools) or "none",
            context="\n".join(
                f"[{ctx.get('source', 'unknown')}] {str(ctx.get('content', ''))[:200]}..."
                for ctx in context_items
            ) or "No context available.",
            errors="\n- ".join(error_items) or "No recent errors.",
            history=history_str or "No history.",
            query=state["messages"][-1].content,
            timestamp=datetime.now().isoformat()
        )

    # Add metrics attribute (or receive it) if LLM calls are tracked here
    def set_metrics_tracker(self, metrics: AgentMetrics):
         self.metrics = metrics
    
class ToolExecutor:
    def __init__(self, registry: ToolRegistry, metrics: AgentMetrics):
        self.registry = registry
        self.metrics = metrics
    
    def execute(self, state: AgentState) -> Dict:
        tool_call = state.get("pending_tool")
        if not tool_call:
            last_message = state.get("messages", [])[-1] if state.get("messages") else None
            if isinstance(last_message, AIMessage):
                fn_call = last_message.additional_kwargs.get("function_call")
                if fn_call:
                    tool_call = {
                        "name": fn_call.get("name"),
                        "arguments": fn_call.get("arguments"),
                    }
                    state["pending_tool"] = tool_call

        if not tool_call:
            return self._handle_error("Missing tool call", state)
        
        tool_name = tool_call.get("name")
        if not self.registry.get_tool(tool_name):
            return self._handle_error(f"Disabled tool: {tool_name}", state)
        
        try:
            result = self._run_tool(tool_name, tool_call["arguments"])
            self._update_metrics(tool_name, success=True)
            state.pop("pending_tool", None)
            return self._format_result(result, tool_name, state)
        except Exception as e:
            self._update_metrics(tool_name, success=False)
            state.pop("pending_tool", None)
            return self._handle_error(str(e), state, tool_name)
    
    def _handle_error(self, error_msg: str, state: AgentState, tool_name: str = None) -> Dict:
        """Handle tool execution errors"""
        if "errors" not in state:
            state["errors"] = []
        
        error_message = f"Tool error: {error_msg}"
        state["errors"].append(error_message)
        
        if tool_name:
            self.registry.record_failure(tool_name)
        
        return {
            "messages": [
                FunctionMessage(
                    content=error_message,
                    name=tool_name if tool_name else "tool_error"
                )
            ]
        }
    
    def _run_tool(self, tool_name: str, arguments: Dict) -> Any:
        """Execute the tool with provided arguments"""
        tool_func = self.registry.get_tool(tool_name)
        if not tool_func:
            raise ValueError(f"Tool '{tool_name}' not found or disabled")
        
        # Handle both string and dict argument formats
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError:
                raise ValueError(f"Invalid JSON arguments: {arguments}")
        
        return tool_func(**arguments)
    
    def _update_metrics(self, tool_name: str, success: bool) -> None:
        """Update usage metrics for the tool"""
        self.metrics.tool_usage[tool_name] = self.metrics.tool_usage.get(tool_name, 0) + 1
        
        if not success:
            self.metrics.tool_errors[tool_name] = self.metrics.tool_errors.get(tool_name, 0) + 1
    
    def _format_result(self, result: Any, tool_name: str, state: AgentState) -> Dict:
        """Format tool execution result"""
        # Add tool to list of used tools
        if "tools_used" not in state:
            state["tools_used"] = []
        if tool_name not in state["tools_used"]:
            state["tools_used"].append(tool_name)
        
        # Add result to context if not already there
        if "context" not in state:
            state["context"] = []
        
        # Convert result to string if not JSON serializable
        result_content = result
        try:
            json.dumps(result)  # Test if serializable
        except (TypeError, ValueError):
            result_content = str(result)
        
        # Add to context
        state["context"].append({
            "source": tool_name,
            "content": result_content,
            "timestamp": datetime.now().isoformat()
        })
        
        # Return function message with result
        return {
            "messages": [
                FunctionMessage(
                    content=json.dumps(result) if not isinstance(result, str) else result,
                    name=tool_name
                )
            ]
        }

# --------------------------
# Main Service
# --------------------------
class AgentOrchestrator:
    def __init__(self):
        # Initialize clients and components
        self.llm = LLMClient(host="llm_service", port=50051)
        self.cpp_llm = CppLLMClient()
        self.chroma = ChromaClient()
        # TODO: ToolClient deprecated - will be replaced with function tools in Phase 2
        # self.tool_client = ToolClient()
        
        # Initialize tool registry and metrics
        self.metrics = AgentMetrics()
        self.config = WorkflowConfig() # Instantiate the config
        self.tool_registry = self._init_tools()

        # Pass dependencies to LLMOrchestrator
        self.llm_orchestrator = LLMOrchestrator(self.llm, self.config, self.tool_registry)
        self.llm_orchestrator.set_metrics_tracker(self.metrics) # Pass metrics tracker

        # Initialize the workflow
        self.workflow = self._init_workflow()
    
    def _init_tools(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register(
            "web_search",
            self._web_search,
            "Web search for real-time information"
        )
        registry.register(
            "math_solver",
            self._math_solver,
            "Solve complex math equations"
        )
        registry.register(
            "cpp_llm_inference",
            self._cpp_llm_inference,
            "Low-latency deterministic inference via native C++ microservice"
        )
        registry.register(
            "schedule_meeting",
            self._schedule_meeting,
            "Schedule calendar events via native C++ adapter (requires person, start_time_iso8601, duration_minutes)"
        )
        return registry
    
    def _init_memory(self) -> SqliteSaver:
        """Initializes the SQLite database for persistent memory storage"""
        db_path = os.path.abspath("agent_memory.sqlite")
        
        try:
            # Create SQLite connection directly
            conn = sqlite3.connect(db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")  # Enable Write-Ahead Logging
            atexit.register(self._close_db_connection, conn)
            
            # Initialize SqliteSaver with raw connection
            memory = SqliteSaver(conn=conn)
            logger.info("Memory system initialized successfully")
            return memory
            
        except Exception as e:
            logger.error(f"Failed to initialize memory system: {str(e)}")
            logger.warning("Falling back to in-memory database")
            return SqliteSaver(conn=sqlite3.connect(":memory:", check_same_thread=False))

    def _close_db_connection(self, conn):
        """Close the SQLite connection properly"""
        if conn:
            logger.info("Closing SQLite database connection")
            try:
                conn.close()
            except Exception as e:
                logger.error(f"Error closing connection: {str(e)}")

    def _init_workflow(self) -> StateGraph:
        """Initializes the agent workflow with memory and execution nodes.
        
        Returns:
            StateGraph: Compiled workflow graph for agent execution
        """
        memory = self._init_memory()
        builder = WorkflowBuilder(memory)
        tool_executor = ToolExecutor(self.tool_registry, self.metrics)
        
        return builder.build(
            agent_node=self._agent_node,
            tool_node=tool_executor.execute
        )
    
    def _agent_node(self, state: AgentState) -> Dict:
        return self.llm_orchestrator.generate_response(state)
    
    def _web_search(self, query: str) -> List[dict]:
        # TODO: Replace with agent_service.tools.web.vertex_search() in Phase 2
        logger.warning("web_search tool is deprecated and will be replaced")
        return [{"error": "web_search tool temporarily disabled during refactoring"}]
    
    def _math_solver(self, expression: str) -> float:
        # TODO: Replace with agent_service.tools.math.solve_math() in Phase 2
        logger.warning("math_solver tool is deprecated and will be replaced")
        return 0.0  # Placeholder return

    def _cpp_llm_inference(self, prompt: str, return_intent: bool = True) -> Dict[str, str]:
        start_time = time.time()
        result = self.cpp_llm.run_inference(prompt)
        duration = time.time() - start_time
        logger.info(
            "cpp-llm tool executed",
            extra={
                "prompt": prompt,
                "duration_ms": int(duration * 1000),
                "intent_payload": result.get("intent_payload"),
            }
        )

        # Update rolling average response time for observability
        call_count = max(self.metrics.llm_calls, 1)
        self.metrics.avg_response_time = (
            (self.metrics.avg_response_time * (call_count - 1)) + duration
        ) / call_count

        if return_intent:
            return result

        return {
            "output": result.get("output", ""),
            "intent_payload": result.get("intent_payload", ""),
        }

    def _schedule_meeting(
        self,
        *,
        person: str,
        start_time_iso8601: str,
        duration_minutes: int | str = 30,
    ) -> Dict[str, object]:
        """Bridge tool that schedules a meeting through the native C++ adapter."""

        if not person:
            raise ValueError("person is required to schedule a meeting")
        if not start_time_iso8601:
            raise ValueError("start_time_iso8601 is required to schedule a meeting")

        try:
            minutes = int(duration_minutes)
        except (TypeError, ValueError):
            raise ValueError("duration_minutes must be an integer") from None

        logger.info(
            "schedule_meeting tool invoked",
            extra={
                "person": person,
                "start_time_iso8601": start_time_iso8601,
                "duration_minutes": minutes,
            },
        )

        result = self.cpp_llm.trigger_schedule_meeting(
            person=person,
            start_time_iso8601=start_time_iso8601,
            duration_minutes=minutes,
        )

        if not result.get("success"):
            message = result.get("message") or "Failed to schedule meeting"
            logger.error("schedule_meeting tool failed", extra={"error": message})
            raise RuntimeError(message)

        payload = {
            "status": "scheduled",
            "message": result.get("message") or "Meeting scheduled successfully",
            "event_identifier": result.get("event_identifier", ""),
            "person": person,
            "start_time_iso8601": start_time_iso8601,
            "duration_minutes": minutes,
        }

        logger.info(
            "schedule_meeting tool succeeded",
            extra={"event_identifier": payload["event_identifier"]},
        )
        return payload

def format_messages_to_prompt(messages: List[BaseMessage]) -> str:
    """Formats a list of LangChain messages into a simple string prompt."""
    prompt_str = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            role = "User"
            content = msg.content
        elif isinstance(msg, AIMessage):
            role = "Assistant"
            content = msg.content
            if msg.additional_kwargs.get("function_call"):
                fc = msg.additional_kwargs["function_call"]
                content += f"\n(Wants to call function '{fc.get('name')}' with args: {fc.get('arguments')}) "
        elif isinstance(msg, FunctionMessage):
            role = "Function"
            content = f"({msg.name}): {msg.content}"
        elif isinstance(msg, SystemMessage):
            role = "System"
            content = msg.content
        else:
            role = "Unknown"
            content = str(msg) # Fallback

        prompt_str += f"{role}: {content}\n"
    return prompt_str.strip()

# --------------------------
# gRPC Service Implementation
# --------------------------
class AgentService(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.orchestrator = AgentOrchestrator()
        self.metrics = AgentMetrics()
    
    def QueryAgent(self, request, context):
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[Req ID: {request_id}] Received query: '{request.user_query}'")
        
        try:
            # Retrieve relevant context from vector store
            initial_context = []
            try:
                results = self.orchestrator.chroma.query(request.user_query)
                if results and isinstance(results, list):
                    initial_context = [
                        {
                            "content": doc.get("text", ""),
                            "source": "vector_db",
                            "metadata": doc.get("metadata", {})
                        }
                        for doc in results[:3] if isinstance(doc, dict)
                    ]
                    logger.info(f"[Req ID: {request_id}] Retrieved {len(initial_context)} context docs")
            except Exception as e:
                logger.warning(f"[Req ID: {request_id}] Context retrieval failed: {str(e)}")
            
            # Set up initial state for workflow
            initial_state = AgentState(
                messages=[HumanMessage(content=request.user_query)],
                context=initial_context,
                tools_used=[],
                errors=[],
                start_time=start_time
            )
            
            # Execute the workflow
            config = {"configurable": {"thread_id": request_id}}
            final_state = None
            
            for step in self.orchestrator.workflow.stream(initial_state, config=config):
                node = list(step.keys())[0]
                final_state = step[node]
                
            if not final_state:
                raise RuntimeError("Workflow returned empty state")
                
            # Extract final answer from messages
            final_answer = "Sorry, I couldn't generate a response."
            messages = final_state.get("messages", [])
            for msg in reversed(messages):
                if isinstance(msg, AIMessage) and msg.content and not msg.additional_kwargs.get("function_call"):
                    final_answer = msg.content
                    break
                    
            # Prepare sources and context for response
            used_context = [
                {"source": c.get("source", "unknown"), "content": str(c.get("content", ""))[:150] + "..."}
                for c in final_state.get("context", []) if c.get("content")
            ]
            
            sources = {
                "tools_used": final_state.get("tools_used", []),
                "errors": final_state.get("errors", [])
            }
            
            processing_time = time.time() - start_time
            logger.info(f"[Req ID: {request_id}] Completed in {processing_time:.2f}s")

            # Update metrics (crude average)
            # A more robust approach would store individual times and calculate average
            current_total_time = self.orchestrator.metrics.avg_response_time * (self.orchestrator.metrics.llm_calls -1) # Approx total time before this call
            new_avg = (current_total_time + processing_time) / self.orchestrator.metrics.llm_calls if self.orchestrator.metrics.llm_calls > 0 else processing_time
            self.orchestrator.metrics.avg_response_time = new_avg

            return agent_pb2.AgentReply(
                final_answer=final_answer,
                context_used=json.dumps(used_context),
                sources=json.dumps(sources)
                # execution_graph=... # Still needs implementation if desired
            )
            
        except Exception as e:
            logger.exception(f"[Req ID: {request_id}] Error processing request: {str(e)}")
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(f"Internal error processing request. ID: {request_id}")
            
            return agent_pb2.AgentReply(
                final_answer=f"I'm sorry, but an error occurred while processing your request. (Request ID: {request_id})",
                sources=json.dumps({"error": str(e), "request_id": request_id})
            )

    def GetMetrics(self, request, context):
        metrics_data = self.orchestrator.metrics                        # Get metrics from orchestrator
        return agent_pb2.MetricsResponse(                               # Assuming MetricsResponse exists in proto
            tool_usage=json.dumps(dict(metrics_data.tool_usage)),       # Convert defaultdict
            tool_errors=json.dumps(dict(metrics_data.tool_errors)),     # Convert defaultdict
            llm_calls=metrics_data.llm_calls,
            avg_response_time=metrics_data.avg_response_time
        )

# --------------------------
# Server Setup
# --------------------------
def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentService(), server)
    
    # Health check setup
    health_pb2_grpc.add_HealthServicer_to_server(health.HealthServicer(), server)
    
    # Reflection setup
    service_names = (
        agent_pb2.DESCRIPTOR.services_by_name['AgentService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)
    
    server.add_insecure_port('[::]:50054')
    server.start()
    server.wait_for_termination()

if __name__ == '__main__':
    serve()