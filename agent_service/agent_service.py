# agent_service.py
import uuid
from typing import TypedDict, Optional, Annotated, List, Dict, Any
from grpc_reflection.v1alpha import reflection
import grpc
from concurrent import futures
import time
import logging
import json
from datetime import datetime
import sqlite3
import atexit

import agent_pb2
import agent_pb2_grpc

from shared.clients.llm_client import LLMClient
from shared.clients.chroma_client import ChromaClient
from shared.clients.tool_client import ToolClient

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, FunctionMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain.tools import tool

from grpc_health.v1 import health, health_pb2_grpc
from grpc_health.v1 import health_pb2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent_service")

# --- State Definition ---
class AgentState(TypedDict):
    messages: Annotated[List[HumanMessage | AIMessage | FunctionMessage | SystemMessage], add_messages]
    context: List[dict]
    tools_used: List[str]
    errors: List[str]
    start_time: float

# --- System Prompt ---
SYSTEM_PROMPT_TEMPLATE = """You are an expert AI assistant with access to real-time information and tools.
Follow these steps:
1. Analyze the user query and available context. The user's latest message is the last message in the history.
2. Decide if any tools are needed based *only* on the latest user query and conversation history. Use web_search for current info, recent events, or time-sensitive topics.
3. If tools are needed, call them. If not, proceed to generate the final answer.
4. Use the conversation history and tool results to provide a comprehensive and accurate final answer. Cite sources from the context where applicable.

Available Tools:
{tools}

Current Context (from previous steps or database):
{context}

Current Time: {timestamp}
"""

# --- Health Check ---
class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )

# --- Helper Functions ---
def format_messages_to_prompt(messages: List[Any]) -> str:
    """Convert LangChain message objects to a single prompt string for the LLM client."""
    formatted_prompt = ""
    for msg in messages:
        if hasattr(msg, "type") and hasattr(msg, "content"):
            role = "System" if msg.type == "system" else "User" if msg.type == "human" else "Assistant" if msg.type == "ai" else "Function"
            formatted_prompt += f"\n\n{role}: {msg.content}"
            
            # Add function call information if available
            if msg.type == "ai" and hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("function_call"):
                fn_call = msg.additional_kwargs["function_call"]
                formatted_prompt += f"\n[Function Call: {fn_call.get('name')}({fn_call.get('arguments', '{}')})]"
            
            # Add function result information
            if msg.type == "function" and hasattr(msg, "name"):
                formatted_prompt += f" [Function: {msg.name}]"
    
    return formatted_prompt.strip()

def extract_function_call_from_text(text: str) -> Optional[Dict[str, Any]]:
    """Extract function call information from LLM response text."""
    import re
    
    # Pattern to match function calls like: "I want to call web_search("quantum computing")" or similar variations
    patterns = [
        r'call\s+(\w+)\s*\(\s*[\'"](.+?)[\'"]\s*\)',  # call web_search("query")
        r'use\s+(\w+)\s*\(\s*[\'"](.+?)[\'"]\s*\)',   # use web_search("query")
        r'invoke\s+(\w+)\s*\(\s*[\'"](.+?)[\'"]\s*\)', # invoke web_search("query")
        r'(\w+)\s*\(\s*[\'"](.+?)[\'"]\s*\)'          # web_search("query")
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            function_name = match.group(1)
            function_args = match.group(2)
            return {
                "name": function_name,
                "arguments": json.dumps({"query": function_args})
            }
    
    # Check if any available tool is explicitly mentioned
    tool_names = ["web_search"]  # Update with all available tools
    for tool in tool_names:
        if f"I need to use {tool}" in text or f"I should use {tool}" in text or f"Let me search" in text:
            # Extract a query from the text
            query = text.split("for")[-1].strip().strip('."\'')[:100]  # Simple extraction
            if query:
                return {
                    "name": tool,
                    "arguments": json.dumps({"query": query})
                }
    
    return None

# --- Agent Orchestrator ---
class EnhancedAgentOrchestrator:
    def __init__(self):
        # Initialize clients
        self.llm = LLMClient(host="llm_service", port=50051)
        self.chroma = ChromaClient()
        self.tool_client = ToolClient()

        # Setup SQLite checkpointer
        self.db_connection = sqlite3.connect(":memory:", check_same_thread=False)
        atexit.register(self._close_db_connection)
        self.memory = SqliteSaver(conn=self.db_connection)

        # Verify the checkpointer
        logger.info(f"Initialized checkpointer. Type: {type(self.memory)}")
        if not isinstance(self.memory, SqliteSaver):
            raise TypeError(f"Checkpointer is not of type SqliteSaver, got {type(self.memory)} instead!")

        # Initialize tool registry
        self._initialize_tools()

        # Compile the workflow
        self.workflow = self._create_workflow()

    def _close_db_connection(self):
        """Close the SQLite connection when the application exits."""
        if self.db_connection:
            logger.info("Closing SQLite database connection.")
            self.db_connection.close()
            self.db_connection = None

    def _initialize_tools(self):
        """Initialize all available tools."""
        # Register tools in a dictionary for easy access
        self.tools = {
            "web_search": self.web_search,
            # Add other tools here as needed
        }
        
        # Generate formatted tools list for documentation
        self.formatted_tools = list(self.tools.values())
        
        logger.info(f"Initialized {len(self.tools)} tools: {', '.join(self.tools.keys())}")

    @tool
    def web_search(self, query: str) -> List[dict]:
        """Search the web for current information. Use for questions about recent events, real-time data, or time-sensitive topics."""
        logger.info(f"Executing web_search tool with query: '{query}'")
        try:
            results = self.tool_client.web_search(query)
            if not isinstance(results, list):
                logger.warning(f"Web search tool returned unexpected type: {type(results)}")
                return [{"error": "Web search returned unexpected data format."}]
            return results
        except Exception as e:
            logger.exception(f"Web search tool failed: {str(e)}")
            return [{"error": f"Web search tool failed: {str(e)}"}]

    def _agent_node(self, state: AgentState):
        """Invokes the LLM to determine the next action or generate a response."""
        logger.debug(f"Agent node running. Current state messages count: {len(state.get('messages', []))}")
        try:
            # Prepare context string
            context_str = "\n".join(
                f"[{c.get('source', 'unknown')}] {str(c.get('content', ''))[:200]}..."
                for c in state.get("context", [])
            )
            
            # Build system prompt
            system_prompt_content = SYSTEM_PROMPT_TEMPLATE.format(
                tools="\n".join(f"- {t.name}: {t.description}" for t in self.formatted_tools),
                context=context_str or "No context available yet.",
                timestamp=datetime.now().isoformat()
            )
            
            # Prepare messages for LLM
            messages_for_llm = [SystemMessage(content=system_prompt_content)]
            messages_for_llm.extend(state["messages"][-6:])  # Last 6 messages for context
            
            # Format messages to a single prompt string
            formatted_prompt = format_messages_to_prompt(messages_for_llm)
            
            logger.debug(f"Sending prompt to LLM (length: {len(formatted_prompt)}).")
            
            # Call LLM with properly formatted string prompt
            response_text = self.llm.generate(
                prompt=formatted_prompt,
                max_tokens=1024,
                temperature=0.7
            )
            
            logger.debug(f"LLM raw response received: {response_text[:100]}...")

            if not isinstance(response_text, str):
                raise TypeError(f"LLM returned unexpected type: {type(response_text)}.")

            # Process LLM response - extract function call if present
            ai_message_args = {"content": response_text}
            function_call = extract_function_call_from_text(response_text)
            
            if function_call:
                ai_message_args["additional_kwargs"] = {"function_call": function_call}
                fn_name = function_call.get("name")
                logger.info(f"LLM requested function call: {fn_name}")
                if fn_name:
                    if "tools_used" not in state or state["tools_used"] is None:
                        state["tools_used"] = []
                    state["tools_used"].append(fn_name)

            return {"messages": [AIMessage(**ai_message_args)]}

        except Exception as e:
            logger.exception(f"Agent node error: {str(e)}")
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append(f"AgentNodeError: {str(e)}")
            return {"messages": [AIMessage(content=f"Sorry, I encountered an internal error: {str(e)}")]}

    def _tool_node(self, state: AgentState):
        """Invokes the requested tool with the provided arguments."""
        logger.debug("Tool node running.")
        tool_name = "unknown_tool"
        try:
            last_msg = state["messages"][-1]
            if not isinstance(last_msg, AIMessage) or not last_msg.additional_kwargs.get("function_call"):
                raise ValueError("Tool node reached without a valid function call in the last message.")

            tool_call = last_msg.additional_kwargs["function_call"]
            tool_name = tool_call["name"]
            tool_args_str = tool_call.get("arguments", "{}")

            try:
                tool_args = json.loads(tool_args_str) if tool_args_str else {}
            except json.JSONDecodeError as json_err:
                logger.error(f"Failed JSON decode for tool '{tool_name}' args: {tool_args_str}. Error: {json_err}")
                raise ValueError(f"Invalid arguments format for tool {tool_name}: {json_err}")

            if tool_name not in self.tools:
                raise ValueError(f"Unknown tool requested: {tool_name}")

            logger.info(f"Invoking tool '{tool_name}' with args: {tool_args}")
            result = self.tools[tool_name](**tool_args)

            # Ensure result is JSON serializable
            try:
                result_str = json.dumps(result)
            except TypeError:
                logger.warning(f"Tool '{tool_name}' result not JSON serializable, converting to string.")
                result_str = str(result)

            # Add result to context
            if "context" not in state or state["context"] is None:
                state["context"] = []
            state["context"].append({
                "content": result_str,
                "source": tool_name,
                "timestamp": datetime.now().isoformat()
            })

            return {"messages": [FunctionMessage(content=result_str, name=tool_name)]}

        except Exception as e:
            logger.exception(f"Tool node error for tool '{tool_name}': {str(e)}")
            if "errors" not in state or state["errors"] is None:
                state["errors"] = []
            state["errors"].append(f"ToolNodeError ({tool_name}): {str(e)}")
            return {"messages": [FunctionMessage(content=f"Error executing tool '{tool_name}': {str(e)}", name=tool_name)]}

    def _should_continue(self, state: AgentState):
        """Determines whether to continue the loop or end."""
        last_msg = state["messages"][-1]
        if isinstance(last_msg, AIMessage) and last_msg.additional_kwargs.get("function_call"):
            logger.debug("Decision: Continue to invoke tool.")
            return "invoke_tool"
        logger.debug("Decision: End workflow.")
        return END

    def _create_workflow(self) -> StateGraph:
        """Builds and compiles the LangGraph StateGraph."""
        workflow = StateGraph(AgentState)
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("invoke_tool", self._tool_node)
        workflow.set_entry_point("agent")
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {"invoke_tool": "invoke_tool", END: END}
        )
        workflow.add_edge("invoke_tool", "agent")

        logger.info(f"Compiling workflow with checkpointer. Type: {type(self.memory)}")
        if not hasattr(self.memory, 'get_next_version'):
            logger.error(f"Checkpointer object {self.memory!r} lacks get_next_version method before compile!")
            raise AttributeError("Checkpointer is missing required 'get_next_version' method.")

        compiled_workflow = workflow.compile(checkpointer=self.memory)
        logger.info("LangGraph workflow compiled successfully.")
        return compiled_workflow

# --- gRPC Server ---
class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self):
        self.orchestrator = EnhancedAgentOrchestrator()
        self.request_counter = 0
        self.error_counter = 0
        logger.info("AgentServiceServicer initialized.")

    def QueryAgent(self, request, context):
        self.request_counter += 1
        request_id = str(uuid.uuid4())
        start_time = time.time()
        logger.info(f"[Req ID: {request_id}] Received QueryAgent request: '{request.user_query}'")

        try:
            # Initial context retrieval
            initial_context = []
            try:
                chroma_results = self.orchestrator.chroma.query(request.user_query)
                if chroma_results and isinstance(chroma_results, list):
                    initial_context = [
                        {
                            "content": doc.get("text", ""),
                            "source": "vector_db",
                            "score": doc.get("score", 0.0),
                            "timestamp": datetime.now().isoformat()
                        }
                        for doc in chroma_results[:3] if isinstance(doc, dict)
                    ]
                    logger.info(f"[Req ID: {request_id}] Retrieved {len(initial_context)} initial context docs from Chroma.")
                else:
                    logger.warning(f"[Req ID: {request_id}] Chroma query returned unexpected result or empty list: {chroma_results}")

            except Exception as chroma_err:
                logger.exception(f"[Req ID: {request_id}] Chroma query failed: {chroma_err}")
                initial_context = []

            initial_state = AgentState(
                messages=[HumanMessage(content=request.user_query)],
                context=initial_context,
                tools_used=[],
                errors=[],
                start_time=start_time
            )

            config = {"configurable": {"thread_id": request_id}}
            logger.info(f"[Req ID: {request_id}] Starting workflow stream.")

            final_state = None
            for step in self.orchestrator.workflow.stream(initial_state, config=config):
                last_node = list(step.keys())[0]
                logger.debug(f"[Req ID: {request_id}] Workflow step: Node='{last_node}'")
                final_state = step[last_node]

            if not final_state:
                logger.error(f"[Req ID: {request_id}] Workflow stream finished without producing a final state.")
                raise RuntimeError("Workflow did not return a final state.")

            logger.info(f"[Req ID: {request_id}] Workflow stream finished.")

            # Extract final answer
            final_answer = "Sorry, I couldn't generate a response."
            messages = final_state.get("messages", [])
            if messages:
                final_ai_message = next(
                    (m for m in reversed(messages)
                     if isinstance(m, AIMessage) and not m.additional_kwargs.get("function_call")),
                    None
                )
                if final_ai_message and final_ai_message.content:
                    final_answer = final_ai_message.content

            # Prepare context and sources for reply
            context_list = final_state.get("context", [])
            sources_dict = {
                "tools_used": final_state.get("tools_used", []),
                "errors": final_state.get("errors", []),
            }

            processing_time = time.time() - start_time
            logger.info(f"[Req ID: {request_id}] Sending final answer (Length: {len(final_answer)}). Processing time: {processing_time:.2f}s")

            # Truncate context content for reply
            truncated_context = [
                {"source": c.get("source", "unknown"), "content": str(c.get("content", ""))[:150] + "..."}
                for c in context_list
            ]

            return agent_pb2.AgentReply(
                final_answer=final_answer,
                context_used=json.dumps(truncated_context),
                sources=json.dumps(sources_dict)
            )

        except Exception as e:
            self.error_counter += 1
            processing_time = time.time() - start_time
            logger.exception(f"[Req ID: {request_id}] Unhandled exception in QueryAgent after {processing_time:.2f}s: {str(e)}")
            try:
                context.set_details(f"Internal server error occurred. Please contact support if persists. Request ID: {request_id}")
                context.set_code(grpc.StatusCode.INTERNAL)
            except Exception as grpc_err:
                logger.error(f"[Req ID: {request_id}] Failed to set gRPC error details: {grpc_err}")

            return agent_pb2.AgentReply(
                final_answer=f"System error: An unexpected error occurred while processing your request. (Request ID: {request_id})",
                sources=json.dumps({"errors": [f"UnexpectedWorkflowError: {str(e)}"], "request_id": request_id})
            )

def serve():
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    servicer = AgentServiceServicer()
    agent_pb2_grpc.add_AgentServiceServicer_to_server(servicer, server)

    health_servicer = HealthServicer()
    health_pb2_grpc.add_HealthServicer_to_server(health_servicer, server)

    SERVICE_NAMES = (
        agent_pb2.DESCRIPTOR.services_by_name['AgentService'].full_name,
        health_pb2.DESCRIPTOR.services_by_name['Health'].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(SERVICE_NAMES, server)

    listen_addr = '[::]:50054'
    server.add_insecure_port(listen_addr)
    logger.info(f"Agent Service starting on {listen_addr}")
    server.start()
    logger.info("Agent Service started successfully.")
    server.wait_for_termination()

if __name__ == "__main__":
    serve()