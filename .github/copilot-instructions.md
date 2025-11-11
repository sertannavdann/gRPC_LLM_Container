# GitHub Copilot Instructions - gRPC LLM Agent Framework

## 🎯 Project Philosophy: "Swap, Don't Stack"

This codebase follows strict SOLID principles with an adapter-based architecture. When adding features:
- **Design for swapping**: Create new implementations that can be swapped in/out via interfaces
- **Extend, don't modify**: Use dependency injection and abstract classes instead of changing core logic
- **Minimal changes**: Prefer extracting interfaces from existing code over rewrites

## 🏗️ Architecture Overview

### Service Mesh (4 microservices)
```
ui_service (Next.js) :5001
    ↓ gRPC
orchestrator :50054 (Main entry point)
    ├→ llm_service :50051 (llama.cpp + Qwen 2.5)
    └→ chroma_service :50052 (Vector DB)
```

### Core Components & Patterns

**Orchestrator Service** (`orchestrator/orchestrator_service.py`)
- `OrchestratorService`: gRPC entry point, extracts `thread-id` from metadata
- `AgentWorkflow`: LangGraph StateGraph with tool routing (in `orchestrator/` not `core/`)
- `LLMEngineWrapper`: Adapts gRPC LLM client to LangGraph interface with tool calling support

**LangGraph Workflow** (`core/graph.py`)
- StateGraph nodes: `llm_node` → `tools_node` → `validate_node`
- Smart tool injection: Only include tools in prompt when `_should_use_tools()` detects keywords/patterns
- Iteration control: Max 5 iterations via `validate_node` checking `retry_count`

**Tool Registry** (`tools/registry.py`)
- `LocalToolRegistry`: Unified registry with circuit breaker protection
- Supports `@register` decorator for Python functions
- Auto-generates OpenAI function calling schemas from docstrings
- Circuit breakers protect against cascading failures (3 failures → open circuit)

**Checkpointing** (`core/checkpointing.py`)
- SQLite + WAL mode for conversation persistence
- Thread-based state management (`thread-id` in gRPC metadata)
- Crash recovery: Scans for incomplete threads on startup

### Critical Data Flow

1. **UI → Orchestrator**: gRPC call with optional `thread-id` metadata
2. **Thread Extraction**: `context.invocation_metadata()` extracts thread-id
3. **State Loading**: `SqliteSaver` loads conversation history for thread
4. **Tool Decision**: `_should_use_tools(query)` decides if tools needed (keyword matching)
5. **LLM Generation**: `LLMEngineWrapper.generate()` with conditional tool injection
6. **Tool Execution**: `LocalToolRegistry.call_tool()` with circuit breaker protection
7. **Persistence**: `SqliteSaver.put()` checkpoints state after each node

## 🛠️ Development Workflows

### Building & Testing
```bash
# Generate protobuf stubs (ALWAYS run before building)
make proto-gen

# Build all services
make build

# Force rebuild without cache (when Docker caches stale code)
docker compose build --build-arg CACHE_BUST=$(date +%s) orchestrator

# Start services
make up

# View logs (all services or specific)
make logs
docker compose logs -f orchestrator
```

### Testing Strategy
```bash
# Unit tests (fast, no Docker needed)
pytest tests/unit/ -v

# Integration tests (requires Docker services running)
make up
pytest tests/integration/ -v

# Specific test with verbose output
pytest tests/integration/test_orchestrator_e2e.py::test_query_with_tools -v
```

### Critical Bug Fix Workflow (Docker Cache Issue)
```bash
# PROBLEM: Code changes not appearing in container despite rebuild
# CAUSE: Docker caches COPY layers even when files change

# SOLUTION: Use cache-busting build arg
docker compose build --build-arg CACHE_BUST=$(date +%s) <service_name>

# OR: Full clean rebuild
make clean && make build
```

## 🔧 Code Patterns & Conventions

### Tool Implementation Pattern
```python
# Register tools in orchestrator/agent_workflow.py __init__

@self.registry.register
def my_tool(param: str, optional_param: int = 10) -> dict:
    """
    Brief description for LLM to understand when to use this tool.
    
    Args:
        param (str): Description of required parameter
        optional_param (int): Description of optional parameter
    
    Returns:
        dict: {"status": "success"|"error", "result": ..., "error": ...}
    """
    try:
        result = perform_action(param, optional_param)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}
```

**Important**: Tool return format MUST have `status` key. Registry auto-wraps if missing.

### Message Handling Pattern
```python
# Convert LangChain messages for prompts
def _format_messages(messages: List) -> str:
    prompt = ""
    for msg in messages:
        if isinstance(msg, HumanMessage):
            prompt += f"User: {msg.content}\n"
        elif isinstance(msg, AIMessage):
            prompt += f"Assistant: {msg.content}\n"
        elif isinstance(msg, ToolMessage):
            prompt += f"Tool Result: {msg.content}\n"
    return prompt.strip()
```

### State Initialization Pattern
```python
# CORRECT: Initialize with thread_id, then add query message
state = create_initial_state(conversation_id=thread_id)
state["messages"].append(HumanMessage(content=query))

# WRONG: Don't pass query as conversation_id
# state = create_initial_state(query)  # ❌ Breaks checkpointing
```

### gRPC Protobuf Import Pattern
```python
# In service files: Use local imports
from . import agent_pb2, agent_pb2_grpc  # ✅ Correct

# In shared/generated: Auto-fixed by Makefile sed command
from . import llm_pb2 as llm__pb2  # ✅ Package-scoped import
```

### Circuit Breaker Integration
```python
# Always use registry.call_tool(), never call tools directly
result = self.registry.call_tool("web_search", query="Python")

if result["status"] == "error":
    if "circuit breaker" in result.get("error", "").lower():
        # Circuit open, tool temporarily unavailable
        fallback_response()
    else:
        # Actual tool error
        handle_error(result["error"])
```

## 🚨 Known Issues & Solutions

### **CRITICAL**: Tool Calling Currently Broken (0% success rate)
**Problem**: `LLMEngineWrapper.generate()` always returns `tool_calls: []`  
**Cause**: Local LLMs don't support OpenAI-style function calling  
**Fix**: Implement structured prompting with JSON grammar (see `docs/CRITICAL_FIX_TOOL_CALLING.md`)  
**Status**: 4-6 hours to implement, highest priority fix

### Grammar Parameter Bug (FIXED)
```python
# WRONG: Passes None to protobuf field
grammar = None if format != "json" else json_grammar
request = GenerateRequest(..., grammar=grammar)  # ❌

# RIGHT: Only add grammar if needed
request_params = {"prompt": prompt, "max_tokens": 512}
if response_format == "json":
    request_params["grammar"] = json_grammar
request = GenerateRequest(**request_params)  # ✅
```

### Protobuf Generation (Required before every build)
```bash
# Run this FIRST before building containers
make proto-gen

# This generates:
# - orchestrator/*_pb2*.py
# - llm_service/*_pb2*.py
# - chroma_service/*_pb2*.py
# - shared/generated/*_pb2*.py
```

## 🎨 SOLID Principles in Practice

### Single Responsibility (SRP)
**Anti-pattern**: Avoid "god classes" that handle multiple concerns  
**Pattern**: Separate validation, processing, and response formatting
```python
# ✅ GOOD: Each class has one job
class MessageValidator:
    def validate_message(self, request): ...

class LLMProcessor:
    def generate_response(self, validated_text): ...

class ResponseBuilder:
    def build_response(self, llm_output): ...
```

### Open/Closed Principle (OCP)
**Anti-pattern**: Modifying core service logic for new features  
**Pattern**: Use abstract base classes and interfaces
```python
# ✅ GOOD: Extend without modifying base
class LLMProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str: ...

class QwenProvider(LLMProvider):
    def generate(self, prompt: str) -> str:
        # New implementation doesn't change base
        ...
```

### Dependency Injection Pattern
```python
# ✅ GOOD: Dependencies injected via constructor
class AgentWorkflow:
    def __init__(self, tool_registry, llm_engine, config):
        self.registry = tool_registry  # Swappable
        self.llm = llm_engine          # Swappable
        self.config = config            # Configurable
```

## 🔍 Debugging Techniques

### LLM Service Issues
```bash
# Check if model file exists
docker compose exec llm_service ls -lh /app/models/

# Test llama-cli directly
docker compose exec llm_service ./llama/llama-cli \
  -m ./models/qwen2.5-0.5b-instruct-q5_k_m.gguf \
  -p "Hello" -n 50
```

### Checkpoint Database Issues
```bash
# Inspect SQLite checkpoint database
docker compose exec orchestrator sqlite3 /app/data/agent_memory.sqlite \
  "SELECT thread_id, status, last_updated FROM thread_status;"

# Check WAL mode enabled
docker compose exec orchestrator sqlite3 /app/data/agent_memory.sqlite \
  "PRAGMA journal_mode;"
```

### gRPC Connection Testing
```bash
# Test gRPC health endpoints
grpc_health_probe -addr=localhost:50051  # LLM service
grpc_health_probe -addr=localhost:50054  # Orchestrator
```

### Thread-ID Debugging
```python
# In orchestrator_service.py, add logging
metadata = dict(context.invocation_metadata())
thread_id = metadata.get('thread-id')
logger.info(f"Received thread-id from metadata: {thread_id}")
```

## 📁 Key Files to Know

| File | Purpose | When to Edit |
|------|---------|-------------|
| `orchestrator/orchestrator_service.py` | gRPC entry, LLMEngineWrapper | Adding endpoints, changing LLM wrapper |
| `core/graph.py` | LangGraph StateGraph nodes | Changing workflow logic, routing |
| `tools/registry.py` | Tool registration & circuit breakers | Adding registry features |
| `tools/builtin/*.py` | Built-in tool implementations | Adding/modifying tools |
| `shared/proto/*.proto` | gRPC service definitions | Adding RPC methods/messages |
| `Makefile` | Build automation | Adding build targets |
| `docker-compose.yaml` | Service orchestration | Adding services, changing ports |

## 🚀 Common Tasks

### Adding a New Tool
1. Edit `orchestrator/agent_workflow.py` → Add `@self.registry.register` function in `__init__`
2. Follow docstring format (Args, Returns sections for schema extraction)
3. Return `{"status": "success"|"error", ...}` dict
4. Test with `pytest tests/unit/test_builtin_tools.py -v`

### Adding a New gRPC Service
1. Define `.proto` in `shared/proto/`
2. Run `make proto-gen`
3. Create `{service}/Dockerfile`
4. Add service to `docker-compose.yaml`
5. Create client in `shared/clients/{service}_client.py`

### Changing LLM Parameters
Edit `llm_service/llm_service.py` → `RunInference()` method → llama-cli args

### Modifying Workflow Routing
Edit `core/graph.py` → `_route_after_llm()` or `_route_after_validate()` methods

## 🧪 Testing Philosophy

- **Unit tests** (`tests/unit/`): Fast, no external dependencies, mock gRPC clients
- **Integration tests** (`tests/integration/`): Full Docker stack, real gRPC calls
- **Tool tests**: Mock external APIs (web_search uses SERPER_API_KEY)
- **Coverage target**: >80% for core/ and tools/, >60% for orchestrator/

## 📊 Performance Considerations

- **Tool injection**: Only include tools when needed (saves ~200 tokens per request)
- **Context window**: Limited to last N messages in `core/graph.py` (default: 10)
- **Max iterations**: Hard limit of 5 to prevent infinite loops
- **Circuit breakers**: 3 failures → 60s timeout (configurable in `core/config.py`)

## 🎓 Learning Resources

- **Architecture**: See `ARCHITECTURE.md` for system design
- **Refactoring Plan**: See `docs/EXECUTIVE_SUMMARY.md` for improvement roadmap
- **Tool Fix**: See `docs/CRITICAL_FIX_TOOL_CALLING.md` for structured prompting implementation
- **LangGraph**: [Official Docs](https://langchain-ai.github.io/langgraph/)
