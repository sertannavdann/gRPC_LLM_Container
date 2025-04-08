# agent_service.py
import uuid
from typing import TypedDict, Optional, Annotated, List
from grpc_reflection.v1alpha import reflection
import grpc
from concurrent import futures
import time
import logging
import json
from datetime import datetime
import sqlite3 # Import sqlite3
import atexit # To attempt closing DB connection on exit

import agent_pb2
import agent_pb2_grpc

from shared.clients.llm_client import LLMClient
from shared.clients.chroma_client import ChromaClient
from shared.clients.tool_client import ToolClient

from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
# Ensure direct import for explicit instantiation
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import HumanMessage, AIMessage, FunctionMessage, SystemMessage
from langchain_core.utils.function_calling import convert_to_openai_function
from langchain.tools import tool # Keep using langchain @tool decorator

from grpc_health.v1 import health, health_pb2_grpc
from grpc_health.v1 import health_pb2

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("agent_service")

# --- State Definition --- (No changes needed)
class AgentState(TypedDict):
    messages: Annotated[List[HumanMessage | AIMessage | FunctionMessage | SystemMessage], add_messages]
    context: List[dict]
    tools_used: List[str]
    errors: List[str]
    start_time: float

# --- System Prompt --- (No changes needed)
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

# --- Health Check --- (No changes needed)
class HealthServicer(health.HealthServicer):
    def Check(self, request, context):
        return health_pb2.HealthCheckResponse(
            status=health_pb2.HealthCheckResponse.SERVING
        )

# --- Agent Orchestrator ---
class EnhancedAgentOrchestrator:
    def __init__(self):
        # Initialize clients once
        self.llm = LLMClient(host="llm_service", port=50051)
        self.chroma = ChromaClient()
        self.tool_client = ToolClient()

        # --- Explicit Checkpointer Instantiation ---
        # For :memory:, the connection needs to persist for the lifetime of the orchestrator.
        # check_same_thread=False is needed because gRPC uses a thread pool.
        self.db_connection = sqlite3.connect(":memory:", check_same_thread=False)
        # Ensure connection is closed when the application exits
        atexit.register(self._close_db_connection)

        # Pass the connection object directly to the SqliteSaver constructor
        self.memory = SqliteSaver(conn=self.db_connection)
        # ---------------------------------------------

        # Verify the type right after explicit creation
        logger.info(f"Initialized checkpointer explicitly. Type: {type(self.memory)}, Has get_next_version: {hasattr(self.memory, 'get_next_version')}")
        if not isinstance(self.memory, SqliteSaver):
             # Raise error early if it's still not the correct type
             raise TypeError(f"Checkpointer self.memory is not of type SqliteSaver, got {type(self.memory)} instead!")


        # --- Toolset Definition ---
        # Define tools as methods (as before)
        # The @tool decorator handles schema generation from type hints/docstrings
        self.tools = {
            "web_search": self.web_search,
            # Add other tools here following the same pattern
        }
        # Pre-format tools for the LLM (best practice for efficiency)
        self.formatted_tools = list(self.tools.values())
        self.formatted_functions = [convert_to_openai_function(t) for t in self.formatted_tools]
        # --------------------------

        # Compile the workflow once during initialization
        self.workflow = self._create_workflow()

    def _close_db_connection(self):
        """Callback function to close the SQLite connection."""
        if self.db_connection:
            logger.info("Closing SQLite database connection.")
            self.db_connection.close()
            self.db_connection = None # Avoid trying to close again

    @tool
    def web_search(self, query: str) -> List[dict]:
        """Search the web for current information. Use for questions about recent events, real-time data, or time-sensitive topics."""
        # (Implementation remains good: clear description, type hints, uses shared client, handles errors)
        logger.info(f"Executing web_search tool with query: '{query}'")
        try:
            results = self.tool_client.web_search(query)
            # Basic validation/structuring of results (optional but good)
            if isinstance(results, list):
                return results # Assume ToolClient returns the desired format
            else:
                 logger.warning(f"Web search tool returned unexpected type: {type(results)}")
                 return [{"error": "Web search returned unexpected data format."}]
        except Exception as e:
            logger.exception(f"Web search tool failed internally: {str(e)}")
            # Return consistent error structure
            return [{"error": f"Web search tool failed: {str(e)}"}]

    # _agent_node (No significant changes needed, previous version was reasonable)
    def _agent_node(self, state: AgentState):
        """Invokes the LLM to determine the next action or generate a response."""
        logger.debug(f"Agent node running. Current state messages count: {len(state.get('messages', []))}")
        try:
            context_str = "\n".join(
                f"[{c.get('source', 'unknown')}] {str(c.get('content', ''))[:200]}..."
                for c in state.get("context", [])
            )
            system_prompt_content = SYSTEM_PROMPT_TEMPLATE.format(
                tools="\n".join(f"- {t.name}: {t.description}" for t in self.formatted_tools),
                context=context_str or "No context available yet.",
                timestamp=datetime.now().isoformat()
            )
            messages_for_llm = [SystemMessage(content=system_prompt_content)]
            messages_for_llm.extend(state["messages"][-6:])

            logger.debug(f"Sending {len(messages_for_llm)} messages to LLM.")
            response = self.llm.generate(
                messages=[(f"{m.type}: {m.content}") for m in messages_for_llm], # Adapt if LLMClient expects different format
                functions=self.formatted_functions,
                max_tokens=1024,
                temperature=0.5
            )
            logger.debug(f"LLM raw response received: {response}")

            if not isinstance(response, dict):
                 raise TypeError(f"LLM returned unexpected type: {type(response)}. Response: {response}")

            ai_message_args = {}
            if response.get("function_call"):
                fn_call = response["function_call"]
                # Ensure args are string for AIMessage (LLM might return dict)
                if isinstance(fn_call.get("arguments"), dict):
                    fn_call["arguments"] = json.dumps(fn_call["arguments"])
                elif fn_call.get("arguments") is None:
                     fn_call["arguments"] = "{}" # Ensure it's a valid JSON string

                ai_message_args["additional_kwargs"] = {"function_call": fn_call}
                fn_name = fn_call.get("name")
                logger.info(f"LLM requested function call: {fn_name}")
                if fn_name:
                    if "tools_used" not in state or state["tools_used"] is None: state["tools_used"] = []
                    state["tools_used"].append(fn_name)

            content = response.get("content") or response.get("text") or ""
            ai_message_args["content"] = str(content)

            return {"messages": [AIMessage(**ai_message_args)]}

        except Exception as e:
            logger.exception(f"Agent node error: {str(e)}")
            if "errors" not in state or state["errors"] is None: state["errors"] = []
            state["errors"].append(f"AgentNodeError: {str(e)}")
            return {"messages": [AIMessage(content=f"Sorry, I encountered an internal error: {str(e)}")]}

    # _tool_node (No significant changes needed, previous version was reasonable)
    def _tool_node(self, state: AgentState):
        """Invokes the requested tool with the provided arguments."""
        logger.debug("Tool node running.")
        tool_name = "unknown_tool" # Default for error message if extraction fails early
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
            result = self.tools[tool_name](**tool_args) # Call the tool method

            # Ensure result is JSON serializable for FunctionMessage content
            try:
                # Attempt direct serialization first
                result_str = json.dumps(result)
            except TypeError:
                 logger.warning(f"Tool '{tool_name}' result not JSON serializable, converting to string.")
                 result_str = str(result) # Fallback

            # Append raw result to context if possible, maybe also result_str for simplicity?
            # Storing potentially large/complex raw results needs care.
            if "context" not in state or state["context"] is None: state["context"] = []
            state["context"].append({
                "content": result_str, # Store serialized string in context for safety
                "source": tool_name,
                "timestamp": datetime.now().isoformat()
            })

            return {"messages": [FunctionMessage(content=result_str, name=tool_name)]}

        except Exception as e:
            logger.exception(f"Tool node error for tool '{tool_name}': {str(e)}")
            if "errors" not in state or state["errors"] is None: state["errors"] = []
            state["errors"].append(f"ToolNodeError ({tool_name}): {str(e)}")
            # Return error message in FunctionMessage, using the intended tool name
            return {"messages": [FunctionMessage(content=f"Error executing tool '{tool_name}': {str(e)}", name=tool_name)]}

    # _should_continue (No changes needed)
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

        # Log checkpointer type again just before compile for final verification
        logger.info(f"Compiling workflow with checkpointer. Type: {type(self.memory)}")
        if not hasattr(self.memory, 'get_next_version'):
             logger.error(f"Checkpointer object {self.memory!r} STILL lacks get_next_version method before compile!")
             # Optionally raise an error here to prevent compilation with bad checkpointer
             # raise AttributeError("Checkpointer is missing required 'get_next_version' method.")

        compiled_workflow = workflow.compile(checkpointer=self.memory)
        logger.info("LangGraph workflow compiled successfully.")
        return compiled_workflow

# --- gRPC Server --- (Minor logging/error handling improvements)
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
                # Pass n_results explicitly if needed by your client
                chroma_results = self.orchestrator.chroma.query(request.user_query) # Removed n_results=3, add back if needed
                if chroma_results and isinstance(chroma_results, list):
                    initial_context = [
                        {
                            "content": doc.get("text", ""),
                            "source": "vector_db",
                            "score": doc.get("score", 0.0),
                            "timestamp": datetime.now().isoformat()
                        }
                        for doc in chroma_results[:3] if isinstance(doc, dict) # Limit to top 3
                    ]
                    logger.info(f"[Req ID: {request_id}] Retrieved {len(initial_context)} initial context docs from Chroma.")
                else:
                    logger.warning(f"[Req ID: {request_id}] Chroma query returned unexpected result or empty list: {chroma_results}")

            except Exception as chroma_err:
                 # Log the specific chroma error better
                 logger.exception(f"[Req ID: {request_id}] Chroma query failed: {chroma_err}")
                 initial_context = [] # Proceed with empty context

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

            # Extract final answer (ensure messages list exists)
            final_answer = "Sorry, I couldn't generate a response." # Improved default
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
                 # "initial_context_sources": [c.get("source") for c in initial_context if c.get("source")] # Maybe redundant if context_list includes these?
            }

            processing_time = time.time() - start_time
            logger.info(f"[Req ID: {request_id}] Sending final answer (Length: {len(final_answer)}). Processing time: {processing_time:.2f}s")

            # Truncate context content for reply to avoid large responses
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
                # Try to inform the client about the internal error
                context.set_details(f"Internal server error occurred. Please contact support if persists. Request ID: {request_id}")
                context.set_code(grpc.StatusCode.INTERNAL)
            except Exception as grpc_err:
                 logger.error(f"[Req ID: {request_id}] Failed to set gRPC error details: {grpc_err}")

            # Return a standardized error reply
            return agent_pb2.AgentReply(
                final_answer=f"System error: An unexpected error occurred while processing your request. (Request ID: {request_id})",
                sources=json.dumps({"errors": [f"UnexpectedWorkflowError: {str(e)}"], "request_id": request_id})
            )


def serve():
    # --- Server Setup --- (No changes needed from previous robust version)
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    # Instantiate servicer *once*
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
    server.wait_for_termination() # Blocks until server is stopped

if __name__ == "__main__":
    serve()