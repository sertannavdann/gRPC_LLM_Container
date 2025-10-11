# gRPC LLM Container - AI Agent Instructions

## Architecture Overview (Phase 1 Restructure)

This system provides **local LLM inference** with microservices orchestration, following **Google ADK**, **LangGraph**, and **Model Context Protocol (MCP)** patterns.

### Dual Architecture (Transition Period)
**NEW: Core Framework** (`core/` + `tools/`):
- Type-safe agent workflows (LangGraph StateGraph)
- ADK-style function tools with decorators
- Circuit breakers and SQLite checkpointing
- MCP integration for cross-system tool sharing

**LEGACY: gRPC Services** (backward compatible):
- `agent_service/` (port 50054): LangGraph orchestrator
- `llm_service/` (port 50051): llama.cpp local inference
- `chroma_service/` (port 50052): Vector embeddings
- `external/CppLLM/` (port 50055): Native macOS/iOS integration

**Key Principle**: Agent-as-denominator pattern—`agent_service` orchestrates all operations via gRPC or direct function calls.

### Service Communication
- **Docker**: Use container names as hostnames (`llm_service:50051`)
- **Local dev**: Use `localhost:50051` or `host.docker.internal`
- All clients inherit from `shared/clients/base_client.py` with retry logic and channel pooling

## Development Workflows

### Protocol Buffer Generation
```bash
make proto-gen  # Regenerates *_pb2.py and *_pb2_grpc.py for all services
```
Always run after modifying `.proto` files in `shared/proto/`. The Makefile auto-fixes relative imports with sed.

### Container Management
```bash
make build      # Parallel Docker builds
make up         # Detached service start
make down       # Stop all services
make logs       # Tail all container logs
```

### Testing Without Containers
```bash
conda run -n llm python -m testing_tool.mock_agent_flow
```
Uses mock clients to validate agent workflow logic without Docker stack. See `testing_tool/mock_agent_flow.py` for stubbing patterns.

## Core Framework Patterns (Phase 1A - NEW)

### State Management (`core/state.py`)
Type-safe `AgentState` with Annotated reducers:
```python
from langgraph.graph import add_messages

class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]  # Auto-dedup
    tool_results: list[dict]  # [{tool_name, result, timestamp, latency_ms}]
    next_action: Literal["llm", "tools", "validate", "end"]  # Routing
```

### LangGraph Workflow (`core/graph.py`)
Graph flow: `START → llm_node → [tools_node] → validate_node → [END | loop to llm]`
- Context window limiting prevents token overflow
- Parallel tool execution (max `config.max_tool_calls_per_turn`)
- Iteration control prevents infinite loops

### Circuit Breaker (`tools/circuit_breaker.py`)
Three-state pattern (CLOSED → OPEN → HALF_OPEN):
```python
breaker = CircuitBreaker(max_failures=3, failure_window=timedelta(minutes=5))
if breaker.is_available():
    result = tool(**args)
    breaker.record_success()  # Reset on success
```
Opens after 3 failures in 5 minutes, enters HALF_OPEN after 1 minute for testing.

### Tool Registration (ADK Pattern)
**NEW** (`tools/registry.py`):
```python
@registry.register
def web_search(query: str) -> dict:
    """Search the web. Args: query (str): Search string. Returns: {"status": "success", "results": [...]}"""
```
Auto-extracts OpenAI schema from docstrings. **LEGACY** (`agent_service/agent_service.py`): gRPC stub wrappers.

## LLM Service Specifics

- Uses `llama_cpp` with `n_ctx=2048`, `n_threads=4`
- JSON mode enforces grammar via `JSON_GRAMMAR` string
- Streaming yields incremental `GenerateResponse` with `is_final` flag
- Model path: `llm_service/models/qwen2.5-0.5b-instruct-q5_k_m.gguf`

Token generation validates JSON incrementally. Non-final responses may have `is_valid_json=False`.

## iOS/macOS Integration

The `external/CppLLM/` C++ bridge connects to Swift AppIntents for Siri/Shortcuts. Requires EventKit entitlements. The bridge runs **outside Docker** in development for TCC database access.

Client usage: `CppLLMClient(host="localhost", port=50055)` in non-containerized mode.

## Environment Variables

**Agent Configuration**:
- `AGENT_MAX_ITERATIONS=5` - Max tool→LLM cycles before termination
- `AGENT_TEMPERATURE=0.7` - LLM sampling temperature (0.0-2.0)
- `AGENT_ENABLE_STREAMING=true` - Token-by-token streaming
- `AGENT_CONTEXT_WINDOW=3` - Recent messages to include in LLM context

**Local LLM**:
- `LLM_MODEL_PATH` - Path to GGUF model (default: `inference/models/qwen2.5-0.5b-instruct-q5_k_m.gguf`)
- `LLM_N_CTX=2048` - Context window size
- `LLM_N_THREADS=4` - CPU threads for inference
- `LLM_N_GPU_LAYERS=0` - Layers to offload to Metal GPU (Apple Silicon)

**API Keys**:
- `SERPER_API_KEY` - Web search (free tier at serper.dev)
- `GOOGLE_MAPS_API_KEY` - For MCP Google Maps integration

## Common Pitfalls

1. **Import errors after proto-gen**: Run `make proto-gen` to fix relative imports in `*_grpc.py` files
2. **Circuit breaker tripped**: Check `agent_service` logs for failure counts; reset via `breaker.reset()` or wait 1 min for HALF_OPEN
3. **Docker host resolution**: Use `host.docker.internal` from containers to access host services
4. **Context window overflow**: Set `AGENT_CONTEXT_WINDOW` lower if hitting token limits (default: 3 messages)
5. **Type errors in Phase 1**: Minor Literal mismatches in `core/graph.py:174` are non-blocking (runtime works)
6. **Mixing old/new tools**: Don't register same tool in both `agent_service/agent_service.py` AND `tools/registry.py`
7. **MCP timeout**: MCPToolset connections default to 15s; increase via `connection_params.timeout` for slow servers

## Key Files for Modification

**Phase 1 (NEW Framework)**:
- **Add tool**: Create in `tools/builtin/` with `@registry.register` decorator, follows ADK patterns
- **Agent workflow**: Edit `core/graph.py` nodes (`_llm_node`, `_tools_node`, `_validate_node`)
- **Configuration**: Update `.env` or `core/config.py` for environment-based settings
- **State management**: Modify `core/state.py` TypedDict (impacts graph compatibility)

**Legacy (gRPC Services)**:
- **Add gRPC tool**: Register in `agent_service/agent_service.py`, implement in `tool_service/tool_service.py`
- **LLM behavior**: Modify `llm_service/llm_service.py` (generation config, grammar)
- **Update protocols**: Edit `.proto` in `shared/proto/`, run `make proto-gen`

## Documentation Map

**Phase 1 (NEW)**:
- `PHASE_1_RESTRUCTURE_PLAN.md` - Complete architecture with directory structure
- `PHASE_1_ARCHITECTURE_VISUAL.md` - Visual diagrams and flow charts
- `PHASE_1_QUICK_REFERENCE.md` - Quick start with examples
- `core/`, `tools/` modules - Inline docstrings follow Google style

**Architecture**:
- `docs/00_OVERVIEW.md` - System philosophy and design decisions
- `docs/01_ARCHITECTURE.md` - Component diagrams and data flows
- `docs/02_AGENT_SERVICE.md` - LangGraph workflow (legacy + new)
- `docs/06_MODERNIZATION_STRATEGY.md` - ADK/MCP migration strategy
- `docs/08_ARCHITECTURE_EVOLUTION.md` - Historical context

**Integration**:
- `docs/03_APPLE_INTEGRATION.md` - C++ bridge for iOS/macOS (EventKit, Contacts)
- `docs/04_N8N_INTEGRATION.md` - Visual workflow engine patterns
- `docs/05_TESTING.md` - Test harness and mock patterns

## Local Inference for iOS

This system uses **llama.cpp** for free local inference instead of cloud APIs. For iOS deployment:
- Models must be quantized (q4_k_m, q5_k_m) for mobile memory constraints
- Use CoreML conversion for Metal acceleration on Apple Silicon
- The microservices can run on-device with local gRPC channels (no Docker)
- Agent orchestration logic remains identical across cloud/edge deployments

## Phase 1 Modernization (In Progress)

**Phase 1A** ✅ - Core framework complete:
- `core/state.py`, `core/graph.py`, `core/checkpointing.py`, `core/config.py`
- `tools/base.py`, `tools/circuit_breaker.py`

**Phase 1B** 🔴 - Tool system (next):
- Complete `tools/registry.py` with `@tool` decorator
- Built-in tools: `tools/builtin/{web_search,math_solver,web_loader}.py`
- Unit tests with 80% coverage target

**Phase 1C** 🔴 - MCP integration:
- `tools/mcp/client.py` - MCPToolset for external MCP servers (Google Maps example)
- `tools/mcp/server.py` - Expose ADK tools as MCP server (port 50056)
- Follows Google ADK lab patterns with StdioConnectionParams

**Phase 1D** 🔴 - Observability:
- Prometheus metrics in `monitoring/metrics.py`
- Grafana dashboards (http://localhost:3000)
- OpenTelemetry tracing

### MCP Integration Pattern
```python
# Use external MCP server
from tools.mcp import MCPToolset, StdioConnectionParams
maps = MCPToolset(connection_params=StdioConnectionParams(
    server_params=StdioServerParameters(command='npx', args=["-y", "@modelcontextprotocol/server-google-maps"]),
    timeout=15
))
registry.register_mcp_toolset(maps)
```

See `PHASE_1_RESTRUCTURE_PLAN.md` and `docs/06_MODERNIZATION_STRATEGY.md` for details.
