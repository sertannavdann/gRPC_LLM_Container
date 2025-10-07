# Agent Service Implementation

## Overview

The agent service is the **central orchestrator** of the system. It coordinates between:
- LLM service (reasoning)
- Chroma service (retrieval)
- Tool service (external APIs)
- CppLLM bridge (Apple integration)

**Key Responsibilities**:
1. Accept user queries via gRPC
2. Maintain conversation state
3. Decide which tools to call
4. Execute tools and handle errors
5. Synthesize final answers
6. Persist state for multi-turn conversations

## Architecture

### Class Diagram

```
    ┌──────────────────────────────────────┐
    │           AgentService               │
    │   (gRPC service implementation)      │
    └─────────────┬────────────────────────┘
                  │
                  ▼
    ┌──────────────────────────────────────┐
    │      AgentOrchestrator               │
    │  - ToolRegistry                      │
    │  - LLMOrchestrator                   │
    │  - ToolExecutor                      │
    │  - WorkflowBuilder                   │
    └─────────────┬────────────────────────┘
                  │
        ┌─────────┼─────────┬──────────┐
        ▼         ▼         ▼          ▼
    ┌────────┐ ┌────────┐ ┌────────┐ ┌────────┐
    │  LLM   │ │ Chroma │ │  Tool  │ │ CppLLM │
    │ Client │ │ Client │ │ Client │ │ Client │
    └────────┘ └────────┘ └────────┘ └────────┘
```

## Core Components

### 1. ToolRegistry

**Purpose**: Centralized management of available tools

**Implementation**:
```python
class ToolConfig:
    description: str
    parameters: Dict[str, Any]
    timeout: int = 30
    retries: int = 3
    circuit_breaker_threshold: int = 3

class ToolRegistry:
    def __init__(self):
        self.tools: Dict[str, callable] = {}
        self.configs: Dict[str, ToolConfig] = {}
        self.failures: Dict[str, int] = {}  # Track consecutive failures
    
    def register(self, name: str, func: callable, config: ToolConfig):
        """Register a new tool"""
        self.tools[name] = func
        self.configs[name] = config
        self.failures[name] = 0
    
    def get_tool(self, name: str) -> Optional[callable]:
        """Get tool if available and not circuit-broken"""
        if name not in self.tools:
            return None
        
        # Check circuit breaker
        config = self.configs[name]
        if self.failures[name] >= config.circuit_breaker_threshold:
            logging.warning(f"Tool {name} circuit breaker tripped")
            return None
        
        return self.tools[name]
    
    def record_failure(self, name: str):
        """Increment failure count"""
        self.failures[name] = self.failures.get(name, 0) + 1
    
    def record_success(self, name: str):
        """Reset failure count on success"""
        self.failures[name] = 0
    
    def get_descriptions(self) -> str:
        """Generate tool descriptions for LLM prompt"""
        descriptions = []
        for name, config in self.configs.items():
            if self.failures[name] < config.circuit_breaker_threshold:
                descriptions.append(
                    f"- {name}: {config.description}\n"
                    f"  Parameters: {json.dumps(config.parameters, indent=2)}"
                )
        return "\n\n".join(descriptions)
```

**Why Circuit Breakers**:
- Prevents cascading failures
- Protects external APIs from overload
- Improves error recovery time
- User gets faster "service unavailable" message instead of timeout

**Example Scenario**:
```
Call 1: search_web → API returns 429 (rate limited)
Call 2: search_web → API returns 429
Call 3: search_web → API returns 429
Call 4: search_web → Circuit breaker trips, returns error immediately
```

After circuit trips, tool is unavailable until:
- Manual reset (future: admin API)
- Time-based recovery (future: exponential backoff)
- System restart (current MVP)

### 2. LLMOrchestrator

**Purpose**: Manages LLM interactions and prompt engineering

**Implementation**:
```python
class LLMOrchestrator:
    SYSTEM_PROMPT_TEMPLATE = """
You are a helpful AI assistant with access to tools.

Available Tools:
{tool_descriptions}

Current Context:
{context}

Conversation History:
{history}

Recent Errors:
{errors}

Instructions:
1. Analyze the user's query
2. If you can answer directly, respond with:
   {{"content": "your answer here"}}
3. If you need to use a tool, respond with:
   {{"function_call": {{"name": "tool_name", "arguments": {{"param": "value"}}}}}}
4. Only use available tools
5. Validate parameters before calling tools
6. If previous tool call failed, try a different approach

User Query: {query}
"""
    
    def __init__(self, llm_client, registry: ToolRegistry):
        self.llm = llm_client
        self.registry = registry
        self.max_context_items = 3  # Configurable
        self.max_error_items = 2
    
    def generate_response(self, state: AgentState) -> Dict:
        """Generate LLM response with context"""
        prompt = self._build_prompt(state)
        
        # Stream tokens from LLM
        response_text = ""
        for chunk in self.llm.generate_stream(prompt):
            response_text += chunk.token
        
        # Parse and validate response
        return self.validator.process_response(response_text, state)
    
    def _build_prompt(self, state: AgentState) -> str:
        """Construct prompt from state"""
        return self.SYSTEM_PROMPT_TEMPLATE.format(
            tool_descriptions=self.registry.get_descriptions(),
            context=self._format_context(state.get("context", [])),
            history=self._format_history(state.get("messages", [])),
            errors=self._format_errors(state.get("errors", [])),
            query=self._get_user_query(state)
        )
    
    def _format_context(self, context: List[dict]) -> str:
        """Format recent context (last N items)"""
        recent = context[-self.max_context_items:]
        return "\n".join([
            f"- {item['source']}: {item['content']}"
            for item in recent
        ])
    
    def _format_errors(self, errors: List[str]) -> str:
        """Format recent errors (last N items)"""
        recent = errors[-self.max_error_items:]
        if not recent:
            return "None"
        return "\n".join([f"- {err}" for err in recent])
```

**Key Design Decisions**:

**1. Windowed Context**
- Only last 3 context items sent to LLM
- Prevents context overflow (most models limited to 4k-8k tokens)
- Keeps prompt focused on recent information

**Alternative Approaches**:
- Full history: Wastes tokens, exceeds limits on long conversations
- Summarization: Risks losing important details
- Vector search on history: Complex, adds latency

**2. Error-Aware Prompting**
- Recent errors included in prompt
- Helps LLM avoid repeating mistakes
- Example: If web search failed, LLM might try different tool

**3. JSON-Constrained Output**
- Forces structured responses
- Easy to parse programmatically
- Alternative (free-form text): Requires complex regex, fragile

### 3. ToolExecutor

**Purpose**: Execute tools and handle errors

**Implementation**:
```python
class ToolExecutor:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        self.metrics = {}  # Track latency, success rate
    
    def execute(self, state: AgentState) -> Dict:
        """Execute pending tool call"""
        # 1. Extract tool call
        tool_call = state.get("pending_tool")
        if not tool_call:
            # Fallback: check last AIMessage
            messages = state.get("messages", [])
            last_ai_msg = next((m for m in reversed(messages) 
                               if isinstance(m, AIMessage)), None)
            if last_ai_msg and "function_call" in last_ai_msg.additional_kwargs:
                tool_call = last_ai_msg.additional_kwargs["function_call"]
        
        if not tool_call:
            return self._handle_error("No tool call found", state)
        
        tool_name = tool_call["name"]
        arguments = tool_call.get("arguments", {})
        
        # 2. Validate tool availability
        tool_func = self.registry.get_tool(tool_name)
        if not tool_func:
            return self._handle_error(
                f"Tool {tool_name} unavailable (circuit breaker or not found)",
                state,
                tool_name
            )
        
        # 3. Execute with timeout and retries
        config = self.registry.configs[tool_name]
        for attempt in range(config.retries):
            try:
                start_time = time.time()
                
                # Run tool
                result = tool_func(**arguments)
                
                # Record metrics
                latency = time.time() - start_time
                self._update_metrics(tool_name, latency, success=True)
                self.registry.record_success(tool_name)
                
                # Format success response
                return self._format_result(result, tool_name, state)
                
            except TimeoutError:
                logging.warning(f"Tool {tool_name} timed out (attempt {attempt+1})")
                if attempt == config.retries - 1:
                    self.registry.record_failure(tool_name)
                    return self._handle_error(
                        f"Tool {tool_name} timed out after {config.retries} attempts",
                        state,
                        tool_name
                    )
                time.sleep(2 ** attempt)  # Exponential backoff
                
            except Exception as e:
                logging.error(f"Tool {tool_name} error: {e}")
                self.registry.record_failure(tool_name)
                return self._handle_error(str(e), state, tool_name)
        
        return self._handle_error(f"Tool {tool_name} failed all retries", state, tool_name)
    
    def _format_result(self, result: dict, tool_name: str, state: AgentState) -> Dict:
        """Format successful tool result"""
        # Create FunctionMessage for LangGraph
        function_msg = FunctionMessage(
            name=tool_name,
            content=json.dumps(result)
        )
        
        # Update state
        return {
            "messages": [function_msg],
            "context": state.get("context", []) + [{
                "source": tool_name,
                "content": result
            }],
            "tools_used": state.get("tools_used", []) + [tool_name],
            "pending_tool": None  # Clear pending tool
        }
    
    def _handle_error(self, error_msg: str, state: AgentState, tool_name: str = None) -> Dict:
        """Handle tool execution errors"""
        error_message = FunctionMessage(
            name=tool_name or "unknown",
            content=json.dumps({"error": error_msg})
        )
        
        return {
            "messages": [error_message],
            "errors": state.get("errors", []) + [error_msg],
            "pending_tool": None
        }
    
    def _update_metrics(self, tool_name: str, latency: float, success: bool):
        """Track tool performance"""
        if tool_name not in self.metrics:
            self.metrics[tool_name] = {
                "calls": 0,
                "successes": 0,
                "total_latency": 0
            }
        
        self.metrics[tool_name]["calls"] += 1
        if success:
            self.metrics[tool_name]["successes"] += 1
        self.metrics[tool_name]["total_latency"] += latency
```

**Error Handling Strategy**:
1. **Graceful Degradation**: Errors don't crash the agent
2. **Retry with Backoff**: Transient failures retried with exponential delays
3. **Context Preservation**: Errors added to state for LLM to see
4. **Circuit Breaker Integration**: Repeated failures trip breaker
5. **Metrics Collection**: All calls tracked for observability

### 4. WorkflowBuilder

**Purpose**: Construct the LangGraph state machine

**Implementation**:
```python
from langgraph.graph import StateGraph, END

class WorkflowBuilder:
    def __init__(self, orchestrator: AgentOrchestrator):
        self.orchestrator = orchestrator
    
    def build(self) -> StateGraph:
        """Build LangGraph workflow"""
        # 1. Create graph
        workflow = StateGraph(AgentState)
        
        # 2. Add nodes
        workflow.add_node("agent", self._agent_node)
        workflow.add_node("tool", self._tool_node)
        
        # 3. Set entry point
        workflow.set_entry_point("agent")
        
        # 4. Add conditional edges
        workflow.add_conditional_edges(
            "agent",
            self._should_continue,
            {
                "continue": "tool",  # Route to tool execution
                "end": END           # Finish conversation
            }
        )
        
        # 5. Add edge from tool back to agent
        workflow.add_edge("tool", "agent")
        
        # 6. Compile with memory
        memory = SqliteSaver.from_conn_string(":memory:")
        return workflow.compile(checkpointer=memory)
    
    def _agent_node(self, state: AgentState) -> Dict:
        """LLM reasoning node"""
        return self.orchestrator.llm_orchestrator.generate_response(state)
    
    def _tool_node(self, state: AgentState) -> Dict:
        """Tool execution node"""
        return self.orchestrator.tool_executor.execute(state)
    
    def _should_continue(self, state: AgentState) -> str:
        """Decide whether to continue or end"""
        # Check if there's a pending tool call
        if state.get("pending_tool"):
            return "continue"
        
        # Check if last message is AIMessage with function_call
        messages = state.get("messages", [])
        if messages:
            last_msg = messages[-1]
            if isinstance(last_msg, AIMessage):
                if "function_call" in last_msg.additional_kwargs:
                    return "continue"
        
        # Otherwise, we're done
        return "end"
```

**Execution Flow Example**:

```
User: "Schedule a meeting with Alex tomorrow at 2pm"

Step 1: Entry → agent node
  State: {messages: [HumanMessage(...)]}
  LLM Output: {"function_call": {"name": "schedule_meeting", ...}}
  New State: {pending_tool: {...}}
  Decision: should_continue → "continue"

Step 2: agent → tool node
  State: {pending_tool: {"name": "schedule_meeting", ...}}
  Tool Executor: Call cpp_llm_client.trigger_schedule_meeting(...)
  Tool Result: {"success": true, "message": "Meeting created"}
  New State: {
    messages: [..., FunctionMessage(...)],
    context: [{"source": "schedule_meeting", ...}],
    tools_used: ["schedule_meeting"],
    pending_tool: None
  }

Step 3: tool → agent node
  State: {context: [...], tools_used: [...]}
  LLM Output: {"content": "Meeting with Alex scheduled for tomorrow at 2pm"}
  New State: {messages: [..., AIMessage(...)]}
  Decision: should_continue → "end"

Step 4: END
  Return final answer to user
```

## Tool Registration

### Built-in Tools

```python
class AgentOrchestrator:
    def _register_tools(self):
        """Register all available tools"""
        
        # 1. Schedule meeting (Apple integration)
        self.registry.register(
            "schedule_meeting",
            self._schedule_meeting,
            ToolConfig(
                description="Schedule a calendar meeting with participants",
                parameters={
                    "participant": {
                        "type": "string",
                        "description": "Name of person to meet with"
                    },
                    "start_time": {
                        "type": "string",
                        "description": "ISO 8601 datetime (e.g., 2024-01-15T14:00:00)"
                    },
                    "duration_minutes": {
                        "type": "integer",
                        "description": "Meeting duration in minutes"
                    }
                }
            )
        )
        
        # 2. Web search
        self.registry.register(
            "search_web",
            self._search_web,
            ToolConfig(
                description="Search the web for information",
                parameters={
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Max number of results (default 5)"
                    }
                }
            )
        )
        
        # 3. Document retrieval
        self.registry.register(
            "search_documents",
            self._search_documents,
            ToolConfig(
                description="Search knowledge base for relevant documents",
                parameters={
                    "query": {
                        "type": "string",
                        "description": "Search query"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results (default 3)"
                    }
                }
            )
        )
        
        # 4. Math solver
        self.registry.register(
            "solve_math",
            self._solve_math,
            ToolConfig(
                description="Solve mathematical expressions",
                parameters={
                    "expression": {
                        "type": "string",
                        "description": "Math expression (e.g., '2 + 2', 'sqrt(16)')"
                    }
                }
            )
        )
```

### Tool Implementation Pattern

**Template**:
```python
def _tool_name(self, param1: str, param2: int) -> dict:
    """
    Tool description for developers
    
    Args:
        param1: Description
        param2: Description
    
    Returns:
        dict with 'success' and 'result' or 'error'
    """
    try:
        # 1. Validate inputs
        if not param1:
            return {"success": False, "error": "param1 is required"}
        
        # 2. Call service/API
        result = self.service_client.method(param1, param2)
        
        # 3. Format response
        return {
            "success": True,
            "result": result
        }
    
    except Exception as e:
        logging.error(f"Tool tool_name failed: {e}")
        return {"success": False, "error": str(e)}
```

**Best Practices**:
- Always return dict with `success` boolean
- Include error messages in `error` key
- Log exceptions for debugging
- Validate inputs before calling external services
- Use timeouts for external calls
- Return structured data when possible

## State Persistence

### SQLite Checkpointing

**Why SQLite**:
- Lightweight (no separate database server)
- ACID transactions (safe concurrent access)
- Easy backup (single file)
- Fast for read-heavy workloads

**Schema** (managed by LangGraph):
```sql
CREATE TABLE checkpoints (
    thread_id TEXT,
    checkpoint_id TEXT,
    parent_checkpoint_id TEXT,
    checkpoint BLOB,
    metadata BLOB,
    PRIMARY KEY (thread_id, checkpoint_id)
);
```

**Usage**:
```python
# Initialize checkpointer
memory = SqliteSaver.from_conn_string("./data/agent_state.db")

# Compile workflow with checkpointing
app = workflow.compile(checkpointer=memory)

# Run with thread_id
result = app.invoke(
    input_state,
    config={"configurable": {"thread_id": "user_123_session_1"}}
)

# Resume conversation
follow_up_result = app.invoke(
    follow_up_state,
    config={"configurable": {"thread_id": "user_123_session_1"}}
)
```

**Benefits**:
- Multi-turn conversations preserved
- Can resume after service restart
- Debugging: replay conversations step-by-step
- Auditing: full conversation history

### Thread Management

**Thread ID Strategy**:
- Format: `{user_id}_{session_id}`
- Example: `user_alice_1704931200`

**Cleanup Policy** (future):
```python
# Delete threads older than 30 days
DELETE FROM checkpoints 
WHERE metadata->>'$.created_at' < datetime('now', '-30 days');
```

## Performance Optimizations

### 1. Client Connection Pooling

**Problem**: Creating gRPC channels is expensive (TLS handshake, DNS lookup)

**Solution**:
```python
class AgentOrchestrator:
    def __init__(self):
        # Create clients once, reuse for all requests
        self.llm_client = LLMClient("llm_service:50051")
        self.chroma_client = ChromaClient("chroma_service:50052")
        self.tool_client = ToolClient("tool_service:50053")
        self.cpp_llm_client = CppLLMClient("cpp_llm:50055")
```

**Impact**: Reduces per-request latency by ~50ms

### 2. Context Window Limiting

**Problem**: Large contexts waste tokens and increase latency

**Solution**: Only send last N context items to LLM

**Configurable**:
```python
self.max_context_items = int(os.getenv("MAX_CONTEXT_ITEMS", "3"))
```

### 3. Parallel Tool Execution (Future)

**Current**: Tools executed sequentially

**Future**:
```python
# If LLM requests multiple tools
if len(pending_tools) > 1:
    results = await asyncio.gather(*[
        self._execute_tool(tool) for tool in pending_tools
    ])
```

**Use Case**: "Search web AND query documents"

## Monitoring & Observability

### Metrics Collected

```python
self.metrics = {
    "schedule_meeting": {
        "calls": 42,
        "successes": 40,
        "total_latency": 12.5,  # seconds
        "avg_latency": 0.297    # seconds
    },
    "search_web": {
        "calls": 100,
        "successes": 95,
        "total_latency": 45.2,
        "avg_latency": 0.452
    }
}
```

### Future: Prometheus Integration

```python
from prometheus_client import Counter, Histogram

tool_calls = Counter('agent_tool_calls_total', 'Total tool calls', ['tool_name'])
tool_latency = Histogram('agent_tool_latency_seconds', 'Tool latency', ['tool_name'])

def execute(self, state: AgentState) -> Dict:
    tool_name = state["pending_tool"]["name"]
    tool_calls.labels(tool_name=tool_name).inc()
    
    with tool_latency.labels(tool_name=tool_name).time():
        result = tool_func(**arguments)
    
    return result
```

## Next: n8n Integration
See [04_N8N_INTEGRATION.md](./04_N8N_INTEGRATION.md) for workflow automation patterns.
