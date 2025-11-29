"""
LangGraph workflow for agent orchestration.

Implements a clean node-based execution flow with conditional routing,
error handling, and iteration control. Follows LangGraph best practices
for state management and graph construction.
"""

import logging
import re
from typing import Literal, Optional
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage

from .state import AgentState, WorkflowConfig, ToolExecutionResult

logger = logging.getLogger(__name__)


class AgentWorkflow:
    """
    LangGraph-based agent workflow with clean node separation.
    
    Architecture:
        1. llm_node: Generates responses or function calls
        2. tools_node: Executes parallel tool calls
        3. validate_node: Checks iteration limits and errors
        4. Conditional routing based on state.next_action
    
    The graph uses SqliteSaver for conversation checkpointing, enabling
    multi-turn conversations with full history persistence.
    
    Example:
        >>> workflow = AgentWorkflow(tool_registry, llm_engine, config)
        >>> compiled = workflow.compile(checkpointer)
        >>> result = compiled.invoke({"messages": [HumanMessage("Hi!")]})
    """
    
    def __init__(
        self,
        tool_registry,  # LocalToolRegistry
        llm_engine,  # LlamaEngine
        config: WorkflowConfig,
    ):
        """
        Initialize workflow with tool registry and LLM engine.
        
        Args:
            tool_registry: LocalToolRegistry instance with registered tools
            llm_engine: LlamaEngine for local inference
            config: WorkflowConfig with iteration limits and LLM params
        """
        self.registry = tool_registry
        self.llm = llm_engine
        self.config = config
        
        # Build graph structure
        self.graph = self._build_graph()
        
        logger.info(
            f"AgentWorkflow initialized: model={config.model_name}, "
            f"max_iterations={config.max_iterations}"
        )
    
    def _should_use_tools(self, query: str) -> bool:
        """
        Determine if a query requires tool usage.
        
        Uses keyword matching and pattern detection to avoid injecting
        tools into the prompt unnecessarily. This prevents small models
        from hallucinating fake tool calls.
        
        Args:
            query: User's question or request
        
        Returns:
            bool: True if tools should be available, False otherwise
        
        Examples:
            >>> self._should_use_tools("hey") # False
            >>> self._should_use_tools("what is 2+2?") # True (math)
            >>> self._should_use_tools("search for Python") # True (web_search)
        """
        query_lower = query.lower()
        
        # Keywords indicating tool usage
        tool_keywords = {
            # Web search indicators
            'search', 'find', 'look up', 'google', 'web', 'online',
            'latest', 'current', 'recent', 'news', 'today',
            
            # Math indicators
            'calculate', 'compute', 'solve', 'math', 'equation',
            'sum', 'multiply', 'divide', 'subtract', 'add',
            
            # Web loading indicators
            'load', 'fetch', 'get', 'download', 'scrape',
            'website', 'url', 'page', 'link',
        }
        
        # Check for tool keywords
        if any(keyword in query_lower for keyword in tool_keywords):
            logger.info(f"Tool usage detected via keywords")
            return True
        
        # Check for mathematical expressions (e.g., "2+2", "15*23")
        if re.search(r'\d+\s*[\+\-\*/\^]\s*\d+', query):
            logger.info(f"Tool usage detected via math expression")
            return True
        
        # Check for URLs
        if re.search(r'https?://', query_lower):
            logger.info(f"Tool usage detected via URL")
            return True
        
        # Conversational greetings/small talk - NEVER need tools
        greeting_patterns = [
            'hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon',
            'good evening', 'how are you', 'how do you do', 'whats up', "what's up",
            'nice to meet', 'thanks', 'thank you', 'bye', 'goodbye', 'see you'
        ]
        if any(pattern in query_lower for pattern in greeting_patterns):
            logger.info(f"Conversational greeting detected - no tools needed")
            return False
        
        # Factual question detection: question words about specific topics
        # Only trigger if it's clearly asking for external information
        factual_keywords = ['what is', 'who is', 'when did', 'where is', 'why did', 
                           'how does', 'how did', 'tell me about', 'explain']
        
        # Questions that clearly need external data
        if any(kw in query_lower for kw in factual_keywords):
            # But exclude simple opinion questions
            opinion_words = ['think', 'feel', 'opinion', 'prefer', 'like', 'favorite']
            if not any(w in query_lower for w in opinion_words):
                logger.info(f"Factual question detected - tools may be needed")
                return True
        
        logger.info(f"No tool usage needed for query")
        return False
    
    def _build_graph(self) -> StateGraph:
        """
        Construct LangGraph workflow with nodes and edges.
        
        Graph structure:
            START -> llm -> [tool | validate | END]
            tool -> validate
            validate -> [llm | END]
        
        Returns:
            StateGraph: Compiled workflow graph
        """
        workflow = StateGraph(AgentState)
        
        # Add processing nodes
        workflow.add_node("llm", self._llm_node)
        workflow.add_node("tools", self._tools_node)
        workflow.add_node("validate", self._validate_node)
        
        # Set entry point
        workflow.set_entry_point("llm")
        
        # Add conditional routing from LLM
        workflow.add_conditional_edges(
            "llm",
            self._route_after_llm,
            {
                "tools": "tools",
                "validate": "validate",
                "end": END,
            },
        )
        
        # Tools always go to validation
        workflow.add_edge("tools", "validate")
        
        # Validation routes to LLM or END
        workflow.add_conditional_edges(
            "validate",
            self._route_after_validate,
            {
                "llm": "llm",
                "end": END,
            },
        )
        
        return workflow
    
    def _llm_node(self, state: AgentState) -> AgentState:
        """
        LLM generation node with function calling support.
        
        Extracts recent messages (context_window), formats with available
        tools, and generates response. Handles both direct replies and
        function calls.
        
        Args:
            state: Current agent state with message history
        
        Returns:
            AgentState: Updated state with AI response and routing decision
        """
        messages = state["messages"]
        
        # Apply context window to prevent token overflow
        recent_messages = messages[-self.config.context_window:]
        
        # Extract last user query to determine if tools are needed
        last_user_message = next(
            (m.content for m in reversed(messages) if isinstance(m, HumanMessage)),
            ""
        )
        # Ensure it's a string
        if isinstance(last_user_message, list):
            last_user_message = " ".join(str(item) for item in last_user_message)
        elif not isinstance(last_user_message, str):
            last_user_message = str(last_user_message)
        
        # Smart tool injection: only include tools if query suggests they're needed
        if self._should_use_tools(last_user_message):
            tools_schema = self.registry.to_openai_tools()
            logger.info(f"Including {len(tools_schema)} tools in prompt")
        else:
            tools_schema = []  # No tools for simple queries
            logger.info("No tools needed - direct answer expected")
        
        logger.debug(f"Calling LLM with {len(recent_messages)} messages, {len(tools_schema)} tools")
        
        try:
            # Call local LLM via llama.cpp
            response = self.llm.generate(
                messages=recent_messages,
                tools=tools_schema,  # ← Now conditional!
                temperature=self.config.temperature,
                max_tokens=1024,  # ← Increased from 512 to allow detailed responses
                stream=self.config.enable_streaming,
            )
            
            # Parse LLM response
            content = response.get("content", "")
            tool_calls = response.get("tool_calls", [])
            
            # Create AI message
            ai_message = AIMessage(
                content=content,
                additional_kwargs={
                    "tool_calls": tool_calls,
                    "model": self.config.model_name,
                },
            )
            
            # Determine next action
            if tool_calls:
                next_action = "tools"
            elif content:
                next_action = "validate"
            else:
                # Empty response, retry
                next_action = "validate"
            
            return {
                **state,
                "messages": [ai_message],
                "next_action": next_action,
                "error": None,
            }
        
        except Exception as e:
            logger.error(f"LLM node error: {e}", exc_info=True)
            return {
                **state,
                "next_action": "end",
                "error": f"LLM generation failed: {str(e)}",
            }
    
    def _tools_node(self, state: AgentState) -> AgentState:
        """
        Tool execution node with parallel calls, error handling, and multi-turn support.
        
        Extracts tool calls from last AI message, executes them in parallel
        (up to max_tool_calls_per_turn), and creates ToolMessage responses.
        
        For multi-turn rollouts (Agent0 style), this node can be invoked multiple
        times within a single query, with each invocation adding tool results
        to the conversation context.
        
        Args:
            state: Current state with tool_calls in last message
        
        Returns:
            AgentState: Updated state with tool results and messages
        """
        last_message = state["messages"][-1]
        tool_calls = last_message.additional_kwargs.get("tool_calls", [])
        
        # Enforce parallel call limit
        tool_calls = tool_calls[:self.config.max_tool_calls_per_turn]
        
        results = []
        tool_messages = []
        
        # Track cumulative tool usage for multi-turn metrics
        total_tool_calls = state.get("total_tool_calls", 0)
        
        logger.info(f"Executing {len(tool_calls)} tool calls (cumulative: {total_tool_calls})")
        
        for tool_call in tool_calls:
            tool_name = tool_call["function"]["name"]
            tool_args = tool_call["function"]["arguments"]
            tool_call_id = tool_call.get("id", f"call_{tool_name}")
            
            start_time = datetime.now()
            
            # Execute tool
            tool = self.registry.get(tool_name)
            if tool:
                try:
                    result = tool(**tool_args)
                    status = result.get("status", "success")
                except Exception as e:
                    logger.error(f"Tool {tool_name} error: {e}", exc_info=True)
                    result = {"status": "error", "error": str(e)}
                    status = "error"
            else:
                result = {
                    "status": "error",
                    "error": f"Tool '{tool_name}' not found or circuit breaker open",
                }
                status = "error"
            
            # Calculate latency
            latency_ms = (datetime.now() - start_time).total_seconds() * 1000
            
            # Record result with metadata
            execution_result = ToolExecutionResult(
                tool_name=tool_name,
                status=status,
                result=result,
                latency_ms=latency_ms,
                error_message=result.get("error") if status == "error" else None,
                retry_count=state.get("retry_count", 0),
            )
            
            results.append(execution_result.to_dict())
            
            # Create tool message for LLM context
            # Format result for better LLM comprehension
            result_content = self._format_tool_result(tool_name, result)
            tool_messages.append(
                ToolMessage(
                    content=result_content,
                    tool_call_id=tool_call_id,
                    name=tool_name,  # Include tool name for multi-turn context
                )
            )
            
            total_tool_calls += 1
        
        return {
            **state,
            "messages": tool_messages,
            "tool_results": state.get("tool_results", []) + results,
            "total_tool_calls": total_tool_calls,
            "next_action": "validate",
        }
    
    def _format_tool_result(self, tool_name: str, result: dict) -> str:
        """
        Format tool result for LLM comprehension.
        
        Converts raw dict results into a readable string format that
        helps the LLM understand and reason about the tool output.
        
        Args:
            tool_name: Name of the tool that was executed
            result: Raw result dictionary from tool execution
        
        Returns:
            str: Formatted result string
        """
        status = result.get("status", "unknown")
        
        if status == "error":
            error_msg = result.get("error", "Unknown error")
            return f"[{tool_name} ERROR]: {error_msg}"
        
        # Extract meaningful data from result
        if "result" in result:
            data = result["result"]
        elif "data" in result:
            data = result["data"]
        elif "formatted" in result:
            data = result["formatted"]
        else:
            # Remove metadata fields for cleaner output
            data = {k: v for k, v in result.items() 
                   if k not in ("status", "_metadata", "latency_ms")}
        
        # Format based on data type
        if isinstance(data, (int, float)):
            return f"[{tool_name} RESULT]: {data}"
        elif isinstance(data, str):
            return f"[{tool_name} RESULT]: {data}"
        elif isinstance(data, dict):
            import json
            return f"[{tool_name} RESULT]: {json.dumps(data, indent=2)}"
        elif isinstance(data, list):
            import json
            return f"[{tool_name} RESULT]: {json.dumps(data, indent=2)}"
        else:
            return f"[{tool_name} RESULT]: {str(result)}"
    
    def _validate_node(self, state: AgentState) -> AgentState:
        """
        Validation and iteration control node.
        
        Checks:
        - Maximum iteration limit reached
        - Error conditions requiring termination
        - Tool results needing LLM interpretation
        
        Args:
            state: Current state with retry_count and tool_results
        
        Returns:
            AgentState: Updated state with routing decision
        """
        retry_count = state.get("retry_count", 0)
        
        # Check max iterations (prevent infinite loops)
        if retry_count >= self.config.max_iterations:
            logger.warning(f"Max iterations ({self.config.max_iterations}) reached")
            return {
                **state,
                "next_action": "end",
                "error": "Maximum iterations exceeded",
            }
        
        # Check for errors
        if state.get("error"):
            logger.error(f"Validation error: {state['error']}")
            return {**state, "next_action": "end"}
        
        # Check if tool results need LLM interpretation
        tool_results = state.get("tool_results", [])
        last_message = state["messages"][-1] if state["messages"] else None
        
        # If we have tool results, route back to LLM for interpretation
        if isinstance(last_message, ToolMessage):
            return {
                **state,
                "retry_count": retry_count + 1,
                "next_action": "llm",
            }
        
        # If AI message has content but no tool calls, we're done
        if isinstance(last_message, AIMessage) and last_message.content:
            tool_calls = last_message.additional_kwargs.get("tool_calls", [])
            if not tool_calls:
                return {**state, "next_action": "end"}
        
        # Default: continue to LLM
        return {
            **state,
            "retry_count": retry_count + 1,
            "next_action": "llm",
        }
    
    def _route_after_llm(
        self, state: AgentState
    ) -> Literal["tools", "validate", "end"]:
        """
        Routing logic after LLM generation.
        
        Args:
            state: Current state with next_action set by llm_node
        
        Returns:
            str: Next node name ("tools", "validate", or "end")
        """
        next_action = state.get("next_action", "end")
        logger.debug(f"Routing after LLM: {next_action}")
        return next_action
    
    def _route_after_validate(
        self, state: AgentState
    ) -> Literal["llm", "end"]:
        """
        Routing logic after validation.
        
        Args:
            state: Current state with next_action set by validate_node
        
        Returns:
            str: Next node name ("llm" or "end")
        """
        next_action = state.get("next_action", "end")
        logger.debug(f"Routing after validation: {next_action}")
        return next_action
    
    def compile(self, checkpointer: Optional[SqliteSaver] = None):
        """
        Compile graph with optional checkpointing.
        
        Args:
            checkpointer: SqliteSaver for conversation persistence
        
        Returns:
            Compiled LangGraph app ready for invocation
        
        Example:
            >>> checkpointer = SqliteSaver.from_conn_string("agent_memory.db")
            >>> app = workflow.compile(checkpointer)
            >>> result = app.invoke(state, config={"thread_id": "conv-123"})
        """
        if checkpointer:
            logger.info("Compiling graph with checkpointing enabled")
        else:
            logger.warning("Compiling graph without checkpointing (ephemeral)")
        
        return self.graph.compile(checkpointer=checkpointer)
