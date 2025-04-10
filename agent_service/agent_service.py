# agent_service.py
import uuid
import grpc
import json
import logging
import time

from datetime import datetime
from typing import Any, Dict, List, Optional, TypedDict
from concurrent import futures
from grpc_reflection.v1alpha import reflection
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from pydantic import BaseModel, ValidationError
from collections import defaultdict

# Protobuf imports
import agent_pb2
import agent_pb2_grpc
from grpc_health.v1 import health, health_pb2_grpc, health_pb2

# Local imports
from shared.clients import LLMClient, ChromaClient, ToolClient
from langchain_core.messages import HumanMessage, AIMessage, FunctionMessage, SystemMessage

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

class ToolResponse(BaseModel):
    content: str
    success: bool
    error: Optional[str] = None

# --------------------------
# Core Components
# --------------------------
class ToolRegistry:
    def __init__(self):
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
# Orchestrates the sequential execution steps of an agent system, 
# Determining when to use tools and when to terminate processing
    def __init__(self, memory: SqliteSaver):
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
    def process_response(self, response: str, state: AgentState) -> Dict:
        """Process and validate the response from the LLM."""
        try:
            # Try to parse the JSON response
            if isinstance(response, str):
                try:
                    parsed = json.loads(response)
                except json.JSONDecodeError:
                    # If response is not valid JSON, wrap it in a basic structure
                    parsed = {"content": response}
            else:
                parsed = response
                
            # Check if the parsed response has a tool call
            if "function_call" in parsed or "tool_call" in parsed:
                tool_call = parsed.get("function_call") or parsed.get("tool_call")
                
                # Update state with pending tool call
                state["pending_tool"] = {
                    "name": tool_call.get("name"),
                    "arguments": tool_call.get("arguments")
                }
                
                # Return AIMessage with function_call
                return {
                    "messages": [
                        AIMessage(
                            content="",
                            additional_kwargs={"function_call": tool_call}
                        )
                    ]
                }
            else:
                # Return a regular AIMessage with content
                content = parsed.get("content", parsed)
                if isinstance(content, dict):
                    content = json.dumps(content)
                    
                return {
                    "messages": [AIMessage(content=content)]
                }
                
        except Exception as e:
            # Handle any error in response processing
            error_msg = f"Error processing LLM response: {str(e)}"
            if "errors" not in state:
                state["errors"] = []
            state["errors"].append(error_msg)
            
            # Return a basic error message
            return {
                "messages": [
                    AIMessage(content=f"I encountered an error processing the request. {error_msg}")
                ]
            }

class LLMOrchestrator:
    SYSTEM_PROMPT = """..."""  # Your prompt template
    
    def __init__(self, llm_client: LLMClient):
        self.llm = llm_client
        self.validator = ResponseValidator()
    
    def generate_response(self, state: AgentState, tools: List[str]) -> Dict:
        prompt = self._build_prompt(state, tools)
        response = self.llm.generate(prompt, response_format="json")
        return self.validator.process_response(response, state)
    
    def _build_prompt(self, state: AgentState, tools: List[str]) -> str:
        """Enhanced prompt construction with dynamic context handling"""
        context_items = state.get("context", [])[-self.config.context_window:]
        error_items = state.get("errors", [])[-self.config.error_window:]
        
        return self.SYSTEM_PROMPT.format(
            tool_descriptions="\n".join(
                f"- {name}: {self.tool_registry.configs[name].description}"
                for name in tools
            ),
            context="\n".join(
                f"[{ctx.get('source', 'unknown')}] {str(ctx.get('content', ''))[:200]}..."
                for ctx in context_items
            ),
            errors="\n- ".join(error_items),
            history=format_messages_to_prompt(state["messages"][-4:]),
            query=state["messages"][-1].content,
            timestamp=datetime.now().isoformat()
        )
    
class ToolExecutor:
    def __init__(self, registry: ToolRegistry, metrics: AgentMetrics):
        self.registry = registry
        self.metrics = metrics
    
    def execute(self, state: AgentState) -> Dict:
        tool_call = state.get("pending_tool")
        if not tool_call:
            return self._handle_error("Missing tool call", state)
        
        tool_name = tool_call.get("name")
        if not self.registry.get_tool(tool_name):
            return self._handle_error(f"Disabled tool: {tool_name}", state)
        
        try:
            result = self._run_tool(tool_name, tool_call["arguments"])
            self._update_metrics(tool_name, success=True)
            return self._format_result(result, tool_name, state)
        except Exception as e:
            self._update_metrics(tool_name, success=False)
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
        self.llm = LLMClient(host="llm_service", port=50051)
        self.chroma = ChromaClient()
        self.tool_client = ToolClient()
        
        self.metrics = AgentMetrics()
        self.tool_registry = self._init_tools()
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
        return registry
    
    def _init_workflow(self) -> StateGraph:
        memory = SqliteSaver(self._init_memory())
        return WorkflowBuilder(memory).build(
            self._agent_node,
            ToolExecutor(self.tool_registry, self.metrics).execute
        )
    
    def _agent_node(self, state: AgentState) -> Dict:
        return LLMOrchestrator(self.llm).generate_response(
            state, 
            list(self.tool_registry.tools.keys())
        )
    
    def _web_search(self, query: str) -> List[dict]:
        try:
            results = self.tool_client.web_search(query)
            if not isinstance(results, list):
                logger.warning(f"Web search tool returned unexpected type: {type(results)}")
                return [{"error": "Web search returned unexpected data format."}]
            return results
        except Exception as e:
            logger.exception(f"Web search tool failed: {str(e)}")
            return [{"error": f"Web search tool failed: {str(e)}"}]
    
    def _math_solver(self, expression: str) -> float:
        try:
            return self.tool_client.math_solver(expression)
        except Exception as e:
            return {"error": str(e)}

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
            
            return agent_pb2.AgentReply(
                final_answer=final_answer,
                context_used=json.dumps(used_context),
                sources=json.dumps(sources)
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
        return agent_pb2.MetricsResponse(
            tool_usage=json.dumps(self.metrics.tool_usage),
            avg_response_time=self.metrics.avg_response_time
        )

# --------------------------
# Enhanced Error Handling
# --------------------------
class ErrorHandler:
    @staticmethod
    def handle_llm_error(state: AgentState, error: Exception) -> Dict:
        error_msg = f"LLM Error: {str(error)}"
        state["errors"].append(error_msg)
        return {"messages": [AIMessage(content=error_msg)]}

    @staticmethod
    def handle_tool_error(state: AgentState, tool_name: str, error: str) -> Dict:
        error_msg = f"Tool Error ({tool_name}): {error}"
        state["errors"].append(error_msg)
        return {"messages": [FunctionMessage(content=error_msg, name=tool_name)]}

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