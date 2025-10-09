# gRPC LLM Container - AI Agent Instructions

## Architecture Philosophy

**Agent-as-Denominator**: The `agent_service` (port 50054) is the orchestrator for all operations. External systems interface only with the agent, which routes to specialized microservices via gRPC. Circuit breakers, retries, and context management happen centrally in the agent.

## Service Communication Pattern

Services communicate via gRPC with health checks and reflection enabled:
- **LLM Service** (50051): Local llama.cpp inference with Metal acceleration, streaming responses
- **Chroma Service** (50052): Vector embeddings and semantic search
- **Tool Service** (50053): Web search (Serper API) and math solver
- **Agent Service** (50054): LangGraph orchestration with SQLite checkpointing
- **CppLLM Bridge** (50055): Native macOS/iOS EventKit/Contacts integration

All clients inherit from `shared/clients/base_client.py` which manages channel pooling. Docker services use container names as hostnames (e.g., `llm_service:50051`).

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

## Critical Agent Service Patterns

### Circuit Breaker Implementation
Tools fail after 3 consecutive errors (`ToolRegistry.record_failure`). Check `configs[name].circuit_breaker` before routing. Reset manually via `reset_circuit_breaker(tool_name)`.

### LangGraph Workflow State
`AgentState` (TypedDict in `agent_service.py`) flows through:
1. `route_to_llm`: Generates response or function call
2. `route_to_tool`: Executes tool if function_call present
3. `summarize`: Final response assembly

SQLite checkpointing enables conversation continuity via `SqliteSaver` in `WorkflowBuilder`.

### Tool Registration Pattern
```python
registry.register(
    name="web_search",
    func=tool_client.call_tool,
    description="Search the web..."
)
```
Tools are callable wrappers around client methods. Available tools list excludes circuit-broken entries.

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

- `SERPER_API_KEY`: Required for tool_service web search (free tier at serper.dev)
- `.env` file auto-loaded by `tool_service` only

## Common Pitfalls

1. **Import errors after proto-gen**: Run `make proto-gen` to fix relative imports in `*_grpc.py` files
2. **Circuit breaker tripped**: Check `agent_service` logs for failure counts; reset via orchestrator method
3. **Docker host resolution**: Use `host.docker.internal` for host machine access from containers
4. **Stream timeout**: LLM client uses 30s default; adjust `_stream_timeout` for longer generations
5. **Context window overflow**: Agent limits to 3 recent messages (`context_window: int = 3` in WorkflowConfig)

## Key Files for Modification

- **Add new tool**: Register in `agent_service/agent_service.py` `AgentOrchestrator.__init__`, implement in `tool_service/tool_service.py`
- **Change LLM behavior**: Modify `llm_service/llm_service.py` generation config or grammar
- **Adjust agent routing**: Edit `WorkflowBuilder` graph nodes in `agent_service.py`
- **Update protocols**: Edit `.proto` files in `shared/proto/`, then `make proto-gen`

## Documentation Map

- `docs/00_OVERVIEW.md`: Architecture philosophy
- `docs/01_ARCHITECTURE.md`: Component diagrams and data flows
- `docs/02_AGENT_SERVICE.md`: LangGraph workflow details
- `docs/03_APPLE_INTEGRATION.md`: C++ bridge and native APIs
- `docs/05_TESTING.md`: Test harness patterns

## Local Inference for iOS

This system uses **llama.cpp** for free local inference instead of cloud APIs. For iOS deployment:
- Models must be quantized (q4_k_m, q5_k_m) for mobile memory constraints
- Use CoreML conversion for Metal acceleration on Apple Silicon
- The microservices can run on-device with local gRPC channels (no Docker)
- Agent orchestration logic remains identical across cloud/edge deployments

## Modernization Direction (ADK-Inspired)

The project is evolving toward Google ADK/LangChain patterns while maintaining local inference:

### Function Tools Pattern
Tools should be Python functions with structured docstrings (not just gRPC stubs):
```python
def tool_name(param: str) -> Dict[str, Any]:
    """Tool description.
    
    Args:
        param (str): Parameter description
    
    Returns:
        Dict with "status" key: {"status": "success", "data": ...}
    """
```

### Tool Registry
New `LocalToolRegistry` in `agent_service/tools/registry.py` supports:
- Python function tools (ADK-style)
- LangChain tool wrappers
- CrewAI tool wrappers
- Automatic schema extraction from docstrings

### Agent-as-Tool Pattern
Specialized agents can be used as tools in root orchestrator to solve "mixing search and non-search tools" limitation.

### MCP Integration (Future)
Port 50056 will expose tools via Model Context Protocol for cross-system agent interoperability.

See `docs/06_MODERNIZATION_STRATEGY.md` for complete migration plan.
