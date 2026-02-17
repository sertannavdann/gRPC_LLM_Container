"""
LangGraph workflow for agent orchestration.

Implements a clean node-based execution flow with conditional routing,
error handling, and iteration control. Follows LangGraph best practices
for state management and graph construction.
"""

import logging
import os
import re
from typing import Literal, Optional
from datetime import datetime

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.sqlite import SqliteSaver
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage, SystemMessage

from .state import AgentState, WorkflowConfig, ToolExecutionResult
from .context_compactor import compact_context
from shared.billing.run_units import RunUnitCalculator
from shared.billing.usage_store import UsageStore

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-builder system prompt — injected when the LLM detects a build intent
# ---------------------------------------------------------------------------
MODULE_BUILDER_SYSTEM_PROMPT = """\
You are executing a **module build pipeline**. Follow these steps IN ORDER:

1. **build_module(name, category, ...)** — creates the scaffold (manifest, adapter skeleton, tests).
2. **Review the returned `adapter_code`** — the skeleton has placeholder `fetch_raw()` and `transform()` methods.
3. **Customize** `fetch_raw()` and `transform()` for the real API, then call \
**write_module_code(module_id, adapter_code)** with the complete updated source.
4. **validate_module(module_id)** — runs syntax, structure, and sandbox tests.
5. **If validation fails**: read the `errors` and `fix_hints`, fix the code, \
call `write_module_code()` again, and then `validate_module()` again. Repeat \
until it passes or you exhaust your retry budget.
6. **On validation success**: call **install_module(module_id)** to deploy.

RULES:
- Preserve the class name, `@register_adapter` decorator, and imports from the skeleton.
- Only replace the method BODIES of `fetch_raw` and `transform`.
- Every `write_module_code` resets the module to PENDING — you MUST re-validate.
- If a retry-budget notice appears in tool results, respect it.
- NEVER call `install_module` before `validate_module` returns `status: success`.
"""

# Keywords that indicate a module-build intent
_MODULE_BUILD_KEYWORDS = frozenset([
    'build me', 'create a module', 'add integration', 'build a module',
    'build an adapter', 'create an adapter', 'create integration',
    'new module', 'new adapter', 'set up a module', 'make a module',
])


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
        chroma_client=None,  # Optional ChromaClient for context archival
    ):
        """
        Initialize workflow with tool registry and LLM engine.
        
        Args:
            tool_registry: LocalToolRegistry instance with registered tools
            llm_engine: LlamaEngine for local inference
            config: WorkflowConfig with iteration limits and LLM params
            chroma_client: Optional ChromaClient for context compaction archival
        """
        self.registry = tool_registry
        self.llm = llm_engine
        self.config = config
        self.chroma_client = chroma_client

        # Billing / metering
        self._run_unit_calculator = RunUnitCalculator()
        self._usage_store = UsageStore(
            db_path=os.getenv("BILLING_DB_PATH", "data/billing.db")
        )

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
            
            # User context indicators (personal data)
            'commute', 'drive', 'driving', 'traffic', 'eta', 'route',
            'schedule', 'calendar', 'meeting', 'appointment', 'event',
            'budget', 'spending', 'finance', 'money', 'balance', 'account',
            'health', 'steps', 'sleep', 'heart rate', 'fitness', 'wellness',
            'briefing', 'summary', 'day', 'my', 'mine',

            # Finance / bank indicators
            'transaction', 'transactions', 'purchase', 'purchases',
            'bank', 'debit', 'credit', 'merchant', 'expense', 'expenses',
            'income', 'payment', 'payments', 'cost', 'costs',
            'spent', 'bought', 'paid', 'subscription',

            # Knowledge base / RAG indicators
            'knowledge', 'notes', 'documents', 'remember', 'saved',
            'stored', 'recall', 'learned', 'previous',

            # Module building / management indicators
            'build me', 'create a', 'add integration', 'connect to',
            'track my', 'set up', 'module', 'modules', 'integration',
            'adapter', 'install', 'uninstall', 'enable', 'disable',
        }
        
        # Check for tool keywords
        if any(keyword in query_lower for keyword in tool_keywords):
            logger.debug("Tool usage detected via keywords")
            return True
        
        # Check for mathematical expressions (e.g., "2+2", "15*23")
        if re.search(r'\d+\s*[\+\-\*/\^]\s*\d+', query):
            logger.debug("Tool usage detected via math expression")
            return True
        
        # Check for URLs
        if re.search(r'https?://', query_lower):
            logger.debug("Tool usage detected via URL")
            return True
        
        # Conversational greetings/small talk - NEVER need tools
        greeting_patterns = [
            'hello', 'hi', 'hey', 'greetings', 'good morning', 'good afternoon',
            'good evening', 'how are you', 'how do you do', 'whats up', "what's up",
            'nice to meet', 'thanks', 'thank you', 'bye', 'goodbye', 'see you'
        ]
        if any(pattern in query_lower for pattern in greeting_patterns):
            logger.debug("Conversational greeting detected - no tools needed")
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
                logger.debug("Factual question detected - tools may be needed")
                return True
        
        logger.debug("No tool usage needed for query")
        return False

    @staticmethod
    def _is_module_build_intent(query: str) -> bool:
        """Detect whether the query is asking to build/create a module."""
        query_lower = query.lower()
        return any(kw in query_lower for kw in _MODULE_BUILD_KEYWORDS)

    def _is_module_build_session(self, state: AgentState) -> bool:
        """Check if this session involves module-build tool calls."""
        for result in state.get("tool_results", []):
            name = result.get("tool_name", "")
            if name in ("build_module", "write_module_code", "validate_module", "module_pipeline"):
                return True
        return False

    def _get_effective_max_iterations(self, state: AgentState) -> int:
        """Return the iteration limit — higher for module-build sessions."""
        if self._is_module_build_session(state):
            return self.config.module_build_max_iterations
        return self.config.max_iterations
    
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
        
        # Compact context: summarise + archive evicted turns instead of
        # silently dropping them.  Falls back to a simple slice when the
        # LLM summariser or ChromaDB is unavailable.
        conversation_id = state.get("conversation_id", "unknown")
        recent_messages = compact_context(
            messages=messages,
            max_messages=self.config.context_window,
            llm_engine=self.llm,
            chroma_client=self.chroma_client,
            conversation_id=conversation_id,
        )
        
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

            # Inject module-builder system prompt for build intents
            if self._is_module_build_intent(last_user_message):
                recent_messages = [
                    SystemMessage(content=MODULE_BUILDER_SYSTEM_PROMPT),
                    *recent_messages,
                ]
                logger.info("Module-build intent detected — system prompt injected")
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
            
            logger.debug("Tool %s called with args: %r", tool_name, tool_args)
            
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

            # Inject retry budget for module-build tools so the LLM knows
            # how many fix attempts remain
            _module_tools = {"build_module", "write_module_code", "validate_module", "install_module"}
            if tool_name in _module_tools:
                effective_max = self._get_effective_max_iterations(state)
                remaining = max(0, effective_max - state.get("retry_count", 0) - 1)
                result_content += f"\n[Retry budget: {remaining}/{effective_max} iterations remaining]"

            tool_messages.append(
                ToolMessage(
                    content=result_content,
                    tool_call_id=tool_call_id,
                    name=tool_name,  # Include tool name for multi-turn context
                )
            )
            
            total_tool_calls += 1

        # ── Run-unit metering ────────────────────────────────────────
        org_id = state.get("org_id") or "default"
        tier = state.get("tier", "standard")
        request_run_units = 0.0

        for r in results:
            ru = self._run_unit_calculator.calculate_from_latency(
                latency_ms=r.get("latency_ms", 0.0),
                tier=tier,
                tool_name=r.get("tool_name", "default"),
            )
            request_run_units += ru
            try:
                self._usage_store.record(
                    org_id=org_id,
                    tool_name=r.get("tool_name", "unknown"),
                    run_units=ru,
                    tier=tier,
                    user_id=state.get("user_id"),
                    thread_id=state.get("conversation_id"),
                    latency_ms=r.get("latency_ms", 0.0),
                )
            except Exception as e:
                logger.warning(f"Failed to record usage for {r.get('tool_name')}: {e}")

        return {
            **state,
            "messages": tool_messages,
            "tool_results": state.get("tool_results", []) + results,
            "total_tool_calls": total_tool_calls,
            "request_run_units": state.get("request_run_units", 0.0) + request_run_units,
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
        
        # Use module-build budget when applicable
        effective_max = self._get_effective_max_iterations(state)
        
        # Check max iterations (prevent infinite loops)
        if retry_count >= effective_max:
            logger.warning(f"Max iterations ({effective_max}) reached")
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
