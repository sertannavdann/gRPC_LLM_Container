# Critical Issues Analysis - gRPC LLM Agent System

**Date**: 2025-10-25  
**Analysis of**: Logs from production testing session  
**Status**: 🔴 Multiple critical hallucination and flow control issues identified

---

## 🔥 Critical Issues

### 1. **Tool Call Hallucinations - Non-existent Tools**

**Issue**: LLM is suggesting tool calls for tools that don't exist in the registry.

**Evidence from logs**:
```json
{"tool_name": "cpp_llm_inference", "arguments": {"query": "Python documentation in multi threading"}}
```

**Root Cause Analysis**:
- Location: `agent_service/agent_service.py` lines 439-458
- The `_init_tools()` method registers these tools:
  - ✅ `web_search`
  - ✅ `math_solver`
  - ✅ `cpp_llm_inference`
  - ✅ `schedule_meeting`

**Wait, the tool EXISTS!** However, looking at `core/graph.py` and `adapter.py`:
- The NEW architecture uses `tools/registry.py` with `LocalToolRegistry`
- The OLD architecture uses `agent_service.py` with legacy `ToolRegistry`
- **The system is running the NEW architecture** (adapter.py), but it only registers:
  - `web_search`
  - `math_solver`
  - `load_web_page`
  
**Missing**: `cpp_llm_inference` is NOT registered in the new system!

**Location**: `agent_service/adapter.py` lines 110-126

---

### 2. **Tool Calls Not Being Executed - Just Printed**

**Issue**: When LLM suggests a tool call, it's returned to the UI as text instead of being executed.

**Evidence from logs**:
```
ui_service | [API] Agent response: {"tool_name": "web_search", "arguments": {"query": "what's up with you?"}}...
```

**Root Cause Analysis**:

#### Problem 1: JSON Response Format Confusion
The LLM is outputting two different formats:
```json
// Format 1 (wrong - raw display):
{"tool_name": "web_search", "arguments": {"query": "..."}}

// Format 2 (correct - for execution):
{"function_call": {"name": "web_search", "arguments": {"query": "..."}}}
```

**Location**: `agent_service/llm_wrapper.py` line 194
- The `_extract_tool_calls()` method only looks for `function_call` pattern
- It doesn't recognize the `tool_name` format

#### Problem 2: LLM Prompt Inconsistency
**Location**: `agent_service/adapter.py` line 77-90
- System prompt tells LLM to use tools but doesn't enforce JSON structure
- No examples showing the exact format expected

#### Problem 3: Tool Execution Bypass
The workflow in `core/graph.py`:
1. ✅ `_llm_node` generates response
2. ✅ Extracts `tool_calls` from response (line 228)
3. ❌ Routes to "tools" node (line 240) **but extraction fails for wrong format**
4. ❌ If no tool_calls extracted → routes to "validate" → "end"
5. 💥 Result: JSON printed as final answer instead of executing tool

---

### 3. **LLM Knowledge Hallucinations**

**Issue**: LLM provides factually incorrect information.

**Evidence from logs**:
```
Query: "What is Cayyolu in Ankara located?"
Response: "Cayyolu is a city located in Ankara, Turkey. It is known for its historical significance..."
```

**Reality**: Çayyolu is a district in Ankara, NOT a coastal city with beaches (Ankara is landlocked).

**Root Cause**:
- Small 0.5B parameter model (`qwen2.5-0.5b-instruct`) has limited knowledge
- Not using tools when it should (should trigger web_search for factual queries)
- Location: `core/graph.py` line 58-99 - `_should_use_tools()` method

**Current logic**:
```python
def _should_use_tools(self, query: str) -> bool:
    tool_keywords = {'search', 'find', 'look up', 'google', 'web', 'online', ...}
    # Only triggers on specific keywords
```

**Problem**: Query "What is Cayyolu in Ankara located?" doesn't contain trigger keywords!

---

### 4. **Context Loss on Follow-up Queries**

**Issue**: Agent doesn't remember previous context.

**Evidence from logs**:
```
Query 1: "Can you give me information about Python documentation in multi threading?"
Response: {"tool_name": "cpp_llm_inference", ...}

Query 2: "can you elaborate"
Response: "Sorry, I don't understand what you're asking. Could you provide more details or context?"
```

**Root Cause**:
- Location: `ui_service/src/app/api/chat/route.ts` line 18
- Each query is sent as isolated message - no thread_id passed!
- Checkpointing exists but isn't being used

```typescript
const response = await executeAgent(message);
// ❌ No thread_id, no conversation context
```

**Should be**:
```typescript
const response = await executeAgent(message, threadId);
```

---

### 5. **JSON Parsing Issues - Extra Text Contamination**

**Issue**: LLM responses sometimes have extra text after valid JSON, breaking parsing.

**Evidence**: Agent service has workaround in `agent_service.py` line 185-216
```python
# If there's "Extra data" error, try to extract just the JSON part
if "Extra data" in str(e):
    logger.warning(f"Extracting JSON from response with extra data")
```

**Root Cause**:
- Small models struggle with instruction following
- Prompt doesn't strongly enforce "ONLY JSON, nothing else"
- Location: `agent_service/llm_wrapper.py` line 134-160

**Current prompt**:
```
HOW TO CALL A TOOL:
Respond with ONLY this JSON format (no extra text before or after):
```

**Problem**: Instruction is buried in middle of long prompt, model ignores it.

---

### 6. **Inconsistent Tool Call Format Across Codebase**

**Multiple competing formats**:

1. **Legacy format** (agent_service.py):
```json
{"function_call": {"name": "tool", "arguments": {...}}}
```

2. **OpenAI format** (core/graph.py):
```json
{
  "id": "call_12345",
  "type": "function",
  "function": {"name": "tool", "arguments": {...}}
}
```

3. **Wrong format** (what LLM outputs):
```json
{"tool_name": "tool", "arguments": {...}}
```

**Impact**: Tool extraction fails silently, tools not executed.

---

## 🐛 Additional Issues Found

### 7. **Deprecated Code Still Running**
- `agent_service.py` is the OLD legacy service
- `adapter.py` + `core/graph.py` is the NEW refactored architecture
- **Both are present**, causing confusion about which runs
- Logs show warnings: `"ToolRegistry is deprecated. Use tools.registry.LocalToolRegistry instead."`

### 8. **Circuit Breaker Not Resetting**
- Location: `tools/circuit_breaker.py`
- Once a tool fails 3 times, circuit opens
- No automatic recovery or manual reset in UI
- Tool becomes permanently unavailable until restart

### 9. **No Tool Execution Visibility**
- UI shows final answer only
- No indication of:
  - Which tools were called
  - Tool execution results
  - Reasoning chain
  - Errors during tool execution

### 10. **Serper API Key Not Set**
- `web_search` tool requires `SERPER_API_KEY` environment variable
- Location: `tools/builtin/web_search.py` line 31
- **Not configured in docker-compose.yaml**
- All web searches will fail with error

### 11. **No Request Timeout**
- LLM generation can hang indefinitely
- No timeout configured in workflow
- Location: `core/config.py` has `timeout_seconds=30` but not enforced

### 12. **Tool Results Not Fed Back to LLM Properly**
- When tools execute successfully, results are added as `ToolMessage`
- But `_validate_node` checks if last message is `ToolMessage` and routes back to LLM
- **However**: LLM prompt doesn't include tool results in a clear format
- Location: `agent_service/llm_wrapper.py` line 113-131

---

## 🔧 Recommended Fixes (Priority Order)

### Priority 1: Fix Tool Execution Flow

**File**: `agent_service/llm_wrapper.py`

**Change 1**: Update `_extract_tool_calls()` to handle multiple formats:
```python
def _extract_tool_calls(self, content: str, tools: Optional[List[Dict]] = None) -> List[Dict]:
    # Pattern 1: {"function_call": {...}}
    # Pattern 2: {"tool_name": "...", "arguments": {...}}  ← ADD THIS
    # Pattern 3: tool_name(args)
```

**Change 2**: Strengthen JSON extraction prompt:
```python
def _format_tool_schemas(self, tools: List[Dict]) -> str:
    return f"""
YOU MUST RESPOND WITH ONLY ONE OF THESE TWO FORMATS:

FORMAT 1 - Use a tool (NO EXTRA TEXT):
{{"function_call": {{"name": "tool_name", "arguments": {{...}}}}}}

FORMAT 2 - Direct answer (NO JSON):
Your natural language answer here.

DO NOT:
- Mix JSON with text
- Add explanations before/after JSON
- Use partial JSON
"""
```

---

### Priority 2: Register Missing Tools

**File**: `agent_service/adapter.py`

**Change**: Add cpp_llm_inference bridge:
```python
def _register_builtin_tools(self):
    # Existing tools...
    
    # Add cpp_llm_inference bridge
    try:
        from shared.clients.cpp_llm_client import CppLLMClient
        cpp_client = CppLLMClient()
        
        def cpp_llm_bridge(query: str) -> Dict[str, Any]:
            result = cpp_client.run_inference(query)
            return result
        
        # Register as tool
        self.registry.register_function(
            func=cpp_llm_bridge,
            name="cpp_llm_inference",
            description="Low-latency inference via C++ service for time-sensitive queries"
        )
        logger.info("Registered tool: cpp_llm_inference")
    except Exception as e:
        logger.warning(f"Failed to register cpp_llm_inference: {e}")
```

---

### Priority 3: Fix Context Persistence

**File**: `ui_service/src/app/api/chat/route.ts`

**Change**: Add thread management:
```typescript
export async function POST(request: NextRequest) {
  const body = await request.json();
  const { message, threadId } = body;  // ← Add threadId
  
  // Generate thread if not provided
  const conversationId = threadId || `session-${Date.now()}`;
  
  // Call agent with thread context
  const response = await executeAgent(message, conversationId);
  
  return NextResponse.json({
    response: response.final_answer,
    threadId: conversationId,  // ← Return for next request
  });
}
```

**File**: `ui_service/src/lib/grpc-client.ts`

**Change**: Update executeAgent signature:
```typescript
export async function executeAgent(
  query: string,
  threadId?: string
): Promise<AgentReply> {
  // Pass threadId to adapter.process_query()
}
```

---

### Priority 4: Improve Tool Detection

**File**: `core/graph.py`

**Change**: Make tool detection more aggressive:
```python
def _should_use_tools(self, query: str) -> bool:
    query_lower = query.lower()
    
    # Existing keyword checks...
    
    # NEW: Check for question words
    question_words = ['what', 'when', 'where', 'who', 'why', 'how', 'which']
    has_question = any(word in query_lower for word in question_words)
    
    # NEW: Check for proper nouns (capitalized words) - likely need search
    import re
    has_proper_nouns = bool(re.search(r'\b[A-Z][a-z]+\b', query))
    
    # If it's a factual question about specific entities, use tools
    if has_question and has_proper_nouns:
        logger.info(f"Tool usage detected via question + proper noun pattern")
        return True
    
    # Existing logic...
```

---

### Priority 5: Add Tool Execution Visibility

**File**: `agent_service/adapter.py`

**Change**: Return tool execution metadata:
```python
def process_query(self, query: str, thread_id: Optional[str] = None) -> Dict[str, Any]:
    result = self.compiled_workflow.invoke(initial_state, config=config)
    
    # Extract tool execution info
    tool_results = result.get("tool_results", [])
    tools_used = [tr["tool_name"] for tr in tool_results]
    
    return {
        "status": "success",
        "content": content,
        "tool_results": tool_results,  # ← Full details
        "tools_used": tools_used,       # ← Simple list
        "reasoning_chain": [            # ← NEW: Show reasoning
            msg.content for msg in messages 
            if isinstance(msg, (AIMessage, ToolMessage))
        ],
        # ...
    }
```

**File**: `ui_service/src/components/chat/ChatMessage.tsx`

**Change**: Display tool usage:
```tsx
export function ChatMessage({ message }: ChatMessageProps) {
  return (
    <div>
      {/* Existing message display */}
      
      {message.toolsUsed && message.toolsUsed.length > 0 && (
        <div className="mt-2 text-xs text-muted-foreground">
          <span className="font-semibold">Tools used:</span>
          {message.toolsUsed.map(tool => (
            <span key={tool} className="ml-2 px-2 py-1 bg-muted rounded">
              {tool}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
```

---

### Priority 6: Add Serper API Key

**File**: `docker-compose.yaml`

**Change**:
```yaml
services:
  agent_service:
    environment:
      - SERPER_API_KEY=${SERPER_API_KEY}  # ← Add this
```

**File**: `.env` (create if not exists):
```bash
SERPER_API_KEY=your_api_key_here
```

---

## 🧪 Testing Recommendations

### Test Case 1: Tool Execution
```
Query: "Search for LangGraph documentation"
Expected: 
  - Tool: web_search called
  - Result: Links to LangGraph docs
  - UI: Shows "Tools used: web_search"
```

### Test Case 2: Context Persistence
```
Query 1: "What is LangGraph?"
Query 2: "Can you tell me more about it?"
Expected: Second query understands "it" refers to LangGraph
```

### Test Case 3: Proper Noun Detection
```
Query: "What is Çayyolu?"
Expected:
  - Tool: web_search triggered (proper noun detected)
  - Result: Accurate info from web
```

### Test Case 4: Math Calculation
```
Query: "Calculate 234 * 567"
Expected:
  - Tool: math_solver called
  - Result: Exact answer (132,678)
```

---

## 📊 Architecture Improvements Needed

### 1. Unified Tool Call Format
Create a single source of truth for tool call format across entire codebase.

### 2. Streaming Support
Current implementation doesn't support streaming responses.

### 3. Multi-turn Memory Management
Implement proper conversation pruning to prevent context overflow.

### 4. Error Recovery
Add retry logic with exponential backoff for failed tool calls.

### 5. Observability
Add structured logging with trace IDs for debugging multi-service interactions.

---

## 🎯 Summary

**Critical blockers**:
1. ❌ Tool calls not executing (just printing JSON)
2. ❌ Missing cpp_llm_inference in new architecture
3. ❌ No context persistence between messages
4. ❌ Poor tool detection leading to hallucinations

**System Status**: 🔴 Prototype stage - needs fixes before production use

**Estimated Fix Time**: 
- Priority 1-3: 4-6 hours
- Priority 4-6: 2-3 hours
- Total: 1-2 days for stable prototype

---

**Generated**: 2025-10-25  
**Analyzer**: GitHub Copilot  
**Review Status**: Ready for developer review
