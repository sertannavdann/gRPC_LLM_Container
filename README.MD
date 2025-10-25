# gRPC LLM Agent Framework

**Status**: 🚀 Production Ready  
**Python**: 3.12+  
**Architecture**: LangGraph + gRPC Microservices + Adapter Pattern

A modern local LLM agent framework with intelligent tool orchestration, conversation persistence, and clean architecture. Features an adapter-based design that bridges gRPC services to LangGraph workflows with built-in tool execution and context management.

> **🏗️ Architecture**: See [`ARCHITECTURE.md`](./ARCHITECTURE.md) for system design details  
> **� Setup**: See [`UI_SERVICE_SETUP.md`](./UI_SERVICE_SETUP.md) for frontend configuration

---

## ✨ Key Features

### 🎯 Adapter Architecture
- **AgentServiceAdapter**: Clean separation between gRPC and LangGraph core
- **LLMClientWrapper**: Adapts any LLM backend to LangGraph interface
- **Tool Registry**: Unified tool management with circuit breakers
- **Thread-based Context**: Conversation persistence with SQLite checkpointing

### 🛠️ Built-in Tools
- **web_search**: Real-time web search via Serper API
- **math_solver**: Mathematical expression evaluation
- **load_web_page**: Web content extraction and analysis
- **cpp_llm_inference**: Native C++ LLM service integration

### 🔒 Production Features
- **Circuit breakers** for fault-tolerant tool execution
- **Conversation checkpointing** with SQLite + WAL mode
- **Thread-safe operation** with proper connection management
- **Comprehensive logging** for debugging and monitoring

---

## 🏗️ Architecture Overview

### Service Mesh

```
┌─────────────┐
│  UI Service │  Next.js 14 + TypeScript
│   (5000)    │  gRPC-js client with metadata
└──────┬──────┘
       │
       ▼
┌─────────────────┐
│  Agent Service  │  gRPC entry point
│    (50054)      │  • Thread-ID extraction from metadata
└────────┬────────┘  • AgentServiceAdapter orchestration
         │
         ├──────────────────────────┐
         ▼                          ▼
┌──────────────────┐      ┌─────────────────┐
│  Core Framework  │      │  Tool Registry  │
│                  │      │                 │
│  • StateGraph    │      │  • web_search   │
│  • LangGraph     │      │  • math_solver  │
│  • Checkpointing │      │  • web_loader   │
│  • LLMWrapper    │      │  • cpp_llm      │
└────────┬─────────┘      └────────┬────────┘
         │                         │
         ▼                         ▼
┌────────────────────┐      ┌─────────────────┐
│  LLM Service       │      │  Chroma Service │
│    (50051)         │      │    (50052)      │
│                    │      │                 │
│  • llama.cpp       │      │  • Vector DB    │
│  • Qwen 2.5 0.5B   │      │  • Embeddings   │
└────────────────────┘      └─────────────────┘
```

### Key Components

| Component | Purpose | Location |
|-----------|---------|----------|
| **AgentServiceAdapter** | Bridges gRPC ↔ LangGraph workflow | `agent_service/adapter.py` |
| **LLMClientWrapper** | Adapts gRPC LLM to LangGraph interface | `agent_service/llm_wrapper.py` |
| **StateGraph** | Workflow orchestration with tool routing | `core/graph.py` |
| **SqliteSaver** | Conversation checkpointing | `core/checkpointing.py` |
| **LocalToolRegistry** | Tool registration with circuit breakers | `tools/registry.py` |
| **gRPC Clients** | Type-safe service communication | `shared/clients/` |

### Data Flow

1. **User Query** → UI sends message with optional `thread-id` metadata
2. **gRPC Gateway** → Agent service extracts thread-id from metadata
3. **Adapter Layer** → AgentServiceAdapter invokes StateGraph workflow
4. **LLM Decision** → LLMClientWrapper queries llama.cpp for tool calls
5. **Tool Execution** → Registry executes tools with circuit breaker protection
6. **Response** → Workflow returns final answer with sources and context
7. **Persistence** → SqliteSaver checkpoints conversation state

## Architecture Overview

```mermaid

## Service Endpoints

| Service | Port | Health Check |
|---------|------|-------------|
| LLM Service | 50051 | `grpc_health_probe -addr:50051` |
| Chroma Service | 50052 | `grpc_health_probe -addr:50052` |
| Tool Service | 50053 | `grpc_health_probe -addr:50053` |
| Agent Service | 50054 | `grpc_health_probe -addr:50054` |

## Logical Flow Recipes

The orchestrator exposes predictable, typed tool interfaces so you can model flows visually or programmatically.

### Agent Decision Weights

1. **Prompt analysis** — the LLM response validator inspects JSON function calls first. If the payload includes `function_call`, the agent routes to the matching tool.
2. **Circuit breakers** — repeated failures trip the breaker and temporarily remove a tool from the candidate list (weights fall to zero).
3. **Context enrichment** — successful tool calls push documents into context, increasing subsequent LLM relevance scores.
4. **Native intents** — when the C++ service returns `intent_payload`, the agent biases towards native flows (e.g., scheduling) over external APIs.

These steps mirror an n8n/Node-RED graph: each tool is a node, the agent is the router, and output context is the equivalent of a data bucket for downstream nodes.

### Designing n8n-style Workflows

1. **Add an HTTP node** that POSTs to the Agent gRPC proxy (or the testing harness described below) with the `user_query`.
2. **Parse the agent response** (JSON) using a Function node. The `sources.tools_used` field indicates which microservices executed.
3. **Branch on `intent_payload`** to trigger follow-up nodes—e.g., send a confirmation email if the payload contains `schedule_event`.
4. **Persist context** by storing `context_used` entries in your knowledge base. Feed them back via the `context` field on subsequent calls for continuity.

Because the agent already enforces tool availability and cooldown windows, external flows do not need to duplicate those concerns—they simply react to the orchestrator’s summarized outcome.

### Mock Flow Harness

To experiment without Docker:

```bash
conda run -n llm python -m testing_tool.mock_agent_flow
```

The harness stubs every downstream service and prints a full interaction trace. You can adapt the script to validate additional scenarios, or import `run_mock_flow` inside notebooks/tests for smoke validation.

```python
from testing_tool import mock_agent_flow

summary = mock_agent_flow.run_mock_flow("Plan a retrospective with Alex")
print(summary["final_answer"])
```

## Building Custom Flows (n8n Example)

1. **HTTP Trigger** → collects the end-user request (`user_query`).
2. **gRPC / HTTP Request** → call an API gateway that forwards to `AgentService.QueryAgent`.
3. **Switch Node** → branch on `sources.tools_used` (e.g., `schedule_meeting`, `web_search`).
4. **Execute Native Actions** → for `schedule_meeting`, optionally call the C++ service directly via the shared Python client, or simply notify the user using the agent’s final answer.
5. **Store Transcript** → append `final_answer`, context, and metrics to Notion/BigQuery for analytics.

This pattern keeps the agent as the denominator: n8n orchestrates *around* the agent instead of duplicating decision logic.

## Usage Example

```bash
# Query the agent service
curl -X POST http://localhost:50054/agent.v1.AgentService/QueryAgent \
  -H "Content-Type: application/json" \
  -d '{"user_query": "What is the square root of the current temperature in Paris?"}'
```

Sample response:

```json
{
  "final_answer": "The current temperature in Paris is 22°C. The square root is approximately 4.69.",
  "context_used": [
    {"source": "web_search", "content": "Paris weather: 22°C..."},
    {"source": "math_solver", "content": "√22 = 4.690..."}
  ],
  "sources": {

### Sprint 2 Highlights (MVP focus)

- ✅ Added `schedule_meeting` tool wired through the C++ gRPC bridge and Swift App Intents package.
- ✅ Refactored protobuf imports to package-scoped modules for reliable packaging/testing.
- ✅ Added mock harness (`testing_tool/mock_agent_flow.py`) to exercise the orchestrator without launching the full stack.
- ✅ Cleaned out unused models/helpers and repaired the streaming LLM client.

With these changes, the agent is the single arbitration point. All flows—CLI, automated jobs, or low-code builders—call into the agent, which then fans out to services according to tool availability, circuit breakers, and intent payloads returned by the native C++ engine.
    "tools_used": ["web_search", "math_solver"],
    "errors": []
  }
}
```

## Monitoring & Logging

View real-time logs:

```bash
make logs
```

Check service health:

```bash
make health-check
```

## Testing & Mocking

- `pytest testing_tool/tests/test_services_modular.py` — fast modular coverage for clients and service handlers.
- `pytest testing_tool/tests/test_agent_mock_flow.py` — ensures the mock harness exercises the scheduling bridge and context propagation.
- `python -m testing_tool.mock_agent_flow` — interactive demo without infrastructure.

## Roadmap Snapshot

- **Sprint 1 (current):** Deliver shared Swift `AppIntentsPackage` with `ScheduleMeetingIntent` and unit tests (`swift test`).
- **Sprint 2:** Extend `cpp_llm.proto` with intent RPCs and wire Objective-C++ handlers to App Intents.
- **Sprint 3:** Register new agent tools, add OpenTelemetry interceptors, and expose observability dashboards.
- **Sprint 4:** Ship end-to-end tests (XCTest + Python harness) and prep beta rollout.

## Customization Guide

### 1. Add New Tools

```python
# tool_service/tool_service.py
def CallTool(self, request, context):
    if request.tool_name == "new_tool":
        return self._handle_new_tool(request.params)
        
def _handle_new_tool(self, params):
    # Implement tool logic
    return tool_pb2.ToolResponse(...)
```

### 2. Modify Workflow

```python
# agent_service/agent_service.py
class WorkflowBuilder:
    def build(self):
        # Add custom workflow edges
        self.graph.add_node("custom_step", self._custom_node)
        self.graph.add_edge("agent", "custom_step")
```

### 3. Swap LLM Models

```dockerfile
# llm_service/Dockerfile
COPY ./models/new-model.gguf /app/models/
```

## Troubleshooting

### Common Issues

**Missing Protobuf Definitions**
```bash
make proto-gen && make build
```

**Tool Service Failures**
- Verify SERPER_API_KEY in .env
- Check rate limits (50 free requests/day)

**LLM Loading Errors**
- Ensure model file exists in llm_service/models/
- Verify model compatibility with llama.cpp

---

## 🚀 Quick Start

### Prerequisites

- **Docker** and **Docker Compose**
- **Python 3.12+** (for local development)
- **SERPER_API_KEY** for web search (get free key at [serper.dev](https://serper.dev))

### Installation

```bash
# Clone repository
git clone https://github.com/yourusername/grpc_llm.git
cd grpc_llm

# Set up environment variables
echo "SERPER_API_KEY=your_key_here" > .env

# Start all services with Docker
make up

# View logs
make logs
```

### Service Endpoints

| Service | Port | Purpose |
|---------|------|---------|
| **UI Service** | 5000 | Next.js web interface |
| **Agent Service** | 50054 | Main orchestration endpoint |
| **LLM Service** | 50051 | Local language model (Qwen 2.5) |
| **Chroma Service** | 50052 | Vector database for RAG |

### Usage Example

**Via Web UI:**
```bash
# Open browser
open http://localhost:5000

# Start chatting - context persists across messages
# Tools are automatically triggered for queries like:
# - "What is the weather in Paris?" → web_search
# - "Calculate 234 * 567" → math_solver
# - "Tell me about https://example.com" → load_web_page
```

**Via gRPC Client:**
```python
import grpc
from shared.generated import agent_pb2, agent_pb2_grpc

channel = grpc.insecure_channel('localhost:50054')
stub = agent_pb2_grpc.AgentServiceStub(channel)

# First message (creates new thread)
response = stub.QueryAgent(
    agent_pb2.QueryRequest(message="What is Çayyolu in Ankara?")
)
print(response.message)  # Uses web_search tool
thread_id = response.threadId

# Follow-up message (uses context)
metadata = [('thread-id', thread_id)]
response = stub.QueryAgent(
    agent_pb2.QueryRequest(message="Tell me more about it"),
    metadata=metadata
)
print(response.message)  # Remembers previous context
```

---

## 🛠️ Development

### Local Setup (without Docker)

```bash
# Create Python environment
conda create -n llm python=3.12
conda activate llm

# Install dependencies
pip install -r agent_service/requirements.txt
pip install -r llm_service/requirements.txt
pip install -r chroma_service/requirements.txt
pip install -r requirements-test.txt

# Generate protobuf files
python -m grpc_tools.protoc -I ./shared/proto \
  --python_out=./shared/generated \
  --grpc_python_out=./shared/generated \
  shared/proto/*.proto

# Run tests
pytest tests/unit/ -v
pytest tests/integration/ -v
```

### Docker Commands (via Makefile)

```bash
make build        # Build all containers
make up           # Start services in background
make down         # Stop services
make logs         # View logs (all services)
make clean        # Remove containers and volumes
make rebuild      # Clean rebuild (no cache)
```

### Project Structure

```
grpc_llm/
├── agent_service/          # Main orchestration service
│   ├── agent_service.py    # gRPC entry point
│   ├── adapter.py          # AgentServiceAdapter (core logic)
│   ├── llm_wrapper.py      # LLM interface adapter
│   └── Dockerfile
├── core/                   # Framework core
│   ├── graph.py            # StateGraph workflow
│   ├── state.py            # Conversation state
│   ├── checkpointing.py    # SQLite persistence
│   └── config.py           # Configuration management
├── tools/                  # Tool system
│   ├── registry.py         # LocalToolRegistry
│   ├── circuit_breaker.py  # Fault tolerance
│   ├── decorators.py       # @tool decorator
│   └── builtin/            # Built-in tools
│       ├── web_search.py
│       ├── math_solver.py
│       └── web_loader.py
├── shared/                 # Shared code
│   ├── clients/            # gRPC clients
│   ├── generated/          # Protobuf generated code
│   └── proto/              # Protobuf definitions
├── llm_service/            # LLM backend
├── chroma_service/         # Vector database
├── ui_service/             # Next.js frontend
└── tests/                  # Test suite
    ├── unit/               # Unit tests
    └── integration/        # E2E tests
```

---

## 🔧 Customization

### Adding a New Tool

Tools are registered in `agent_service/adapter.py`. Here's how to add one:

```python
# In adapter.py __init__ method:

def my_custom_tool(param1: str, param2: int) -> dict:
    """
    Tool description for LLM.
    
    Args:
        param1: Description of first parameter
        param2: Description of second parameter
    
    Returns:
        dict: {"status": "success", "result": "..."}
    """
    try:
        # Your tool logic here
        result = do_something(param1, param2)
        return {"status": "success", "result": result}
    except Exception as e:
        return {"status": "error", "error": str(e)}

# Register it
self.registry.register(
    name="my_custom_tool",
    description="Clear description for LLM to understand when to use it"
)(my_custom_tool)
```

### Configuring Tool Behavior

Edit `core/config.py`:

```python
@dataclass
class ToolConfig:
    circuit_breaker_threshold: int = 3  # Failures before circuit opens
    circuit_breaker_timeout: int = 60    # Seconds before retry
    max_retries: int = 2                  # Per-tool retry limit
```

### Adjusting LLM Parameters

Edit `llm_service/llm_service.py`:

```python
# In RunInference method:
result = subprocess.run([
    "./llama/llama-cli",
    "-m", "./models/qwen2.5-0.5b-instruct-q5_k_m.gguf",
    "-p", prompt,
    "-n", "512",      # Max tokens
    "-t", "4",        # Threads
    "--temp", "0.7",  # Temperature
    "--top-p", "0.9"  # Nucleus sampling
], ...)
```

### Modifying Workflow Logic

Edit `core/graph.py` to customize the StateGraph:

```python
def _should_use_tools(self, state: ConversationState) -> bool:
    """Customize when tools are triggered"""
    query = state.messages[-1].content.lower()
    
    # Add custom trigger logic
    if "urgent" in query:
        return True
    
    # Default heuristics
    return self._detect_tool_intent(query)
```

---

## 📊 Monitoring & Debugging

### View Logs

```bash
# All services
make logs

# Specific service
docker compose logs -f agent_service
docker compose logs -f llm_service
```

### Check Health

```bash
# Service status
docker compose ps

# Port availability
lsof -i :50054  # Agent service
lsof -i :50051  # LLM service
lsof -i :5000   # UI service
```

### Debug Mode

Enable verbose logging in `agent_service/adapter.py`:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Change from INFO
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
```

### Common Issues

**"Cannot operate on a closed database"**
- Ensure SQLite file has write permissions
- Check if multiple processes are accessing the same DB file
- Solution: Restart with `make down && make up`

**"Name resolution failed for target dns:agent_service"**
- Docker network issue
- Solution: `make down && make clean && make up`

**Web search returns no results**
- Missing SERPER_API_KEY in `.env`
- Rate limit exceeded (50 free requests/day)
- Check logs: `docker compose logs -f agent_service | grep SERPER`

**LLM service not responding**
- Model file missing or corrupted
- Check: `docker compose exec llm_service ls -lh /app/models/`
- Re-download model if needed



---

## 🧪 Testing

### Unit Tests

```bash
# Run all unit tests
pytest tests/unit/ -v

# Test specific modules
pytest tests/unit/test_registry.py -v
pytest tests/unit/test_circuit_breaker.py -v
pytest tests/unit/test_builtin_tools.py -v
```

### Integration Tests

```bash
# Start services first
make up

# Run E2E tests
pytest tests/integration/ -v

# Specific test
pytest tests/integration/test_agent_service_e2e.py::test_query_with_tools -v
```

### Test Coverage

```bash
pytest tests/ --cov=agent_service --cov=core --cov=tools --cov-report=html
open htmlcov/index.html
```

---

## 🎯 How It Works

### Adapter Pattern

The system uses the **Adapter Pattern** to bridge different architectural layers:

```python
# User Query Flow
UI (gRPC-js) 
  → AgentService.QueryAgent(request, metadata)
    → AgentServiceAdapter.process_query(message, thread_id)
      → StateGraph.invoke(initial_state, config)
        → LLMClientWrapper.run_inference(prompt, tools)
          → LLMClient.RunInference(grpc_request)
            → llama.cpp (local model)
```

**Key Adapters:**
- **AgentServiceAdapter**: Converts gRPC requests → LangGraph workflow
- **LLMClientWrapper**: Converts LangGraph interface → gRPC LLM calls
- **Tool wrappers**: Convert Python functions → LangChain tool schema

### Tool Execution Flow

1. **Query Analysis**: LLM determines if tools are needed based on query
2. **Tool Selection**: Workflow matches query intent to available tools
3. **Circuit Breaker Check**: Verifies tool is healthy before execution
4. **Execution**: Tool runs with parameters extracted by LLM
5. **Result Processing**: Tool output is formatted and added to context
6. **Final Response**: LLM synthesizes tool results into natural language

### Context Persistence

```python
# Thread-based conversation tracking
thread_id = "user-123-session-456"

# First message creates checkpoint
state1 = {"messages": [HumanMessage("What is Paris?")]}
checkpointer.put(thread_id, state1)

# Second message loads context
state2 = checkpointer.get(thread_id)
# state2.messages = [HumanMessage("What is Paris?"), AIMessage("Paris is...")]

# Follow-up uses history
state2.messages.append(HumanMessage("Tell me more"))
```

---

## 📚 Architecture Deep Dive

### State Management

```python
@dataclass
class ConversationState:
    messages: List[BaseMessage]        # Full conversation history
    iterations: int                     # Workflow iteration counter
    context: List[Dict[str, Any]]      # Retrieved documents/tool results
    metadata: Dict[str, Any]           # Thread ID, timestamps, etc.
```

### Workflow Graph

```
           ┌─────────────┐
           │    START    │
           └──────┬──────┘
                  │
                  ▼
           ┌─────────────┐
           │  agent_node │──────┐
           │ (LLM decides)│      │
           └──────┬──────┘      │
                  │              │
         ┌────────┴────────┐    │
         │                 │    │
         ▼                 ▼    │
    ┌─────────┐      ┌─────────┐
    │  tools  │      │   END   │
    │ (execute)│      └─────────┘
    └────┬────┘            ▲
         │                 │
         └─────────────────┘
     (loop until complete)
```

### Tool Registry Architecture

```python
class LocalToolRegistry:
    def __init__(self):
        self._tools: Dict[str, ToolWrapper] = {}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
    
    def register(self, name: str):
        """Decorator to register tools"""
        def decorator(func):
            self._tools[name] = ToolWrapper(func)
            self._circuit_breakers[name] = CircuitBreaker(threshold=3)
            return func
        return decorator
    
    def execute(self, name: str, **kwargs):
        """Execute with circuit breaker protection"""
        if self._circuit_breakers[name].is_open():
            raise CircuitOpenError(f"Tool {name} circuit is open")
        
        try:
            result = self._tools[name].run(**kwargs)
            self._circuit_breakers[name].record_success()
            return result
        except Exception as e:
            self._circuit_breakers[name].record_failure()
            raise
```

---

## 🚦 Roadmap

### Current Release (v1.0)
- ✅ Adapter-based architecture
- ✅ SQLite conversation persistence
- ✅ 4 built-in tools with circuit breakers
- ✅ Thread-based context management
- ✅ Next.js web UI with real-time updates

### Planned Features
- [ ] **v1.1**: Streaming responses for better UX
- [ ] **v1.2**: Multi-modal support (images, audio)
- [ ] **v1.3**: Plugin system for external tools
- [ ] **v1.4**: Observability dashboard (OpenTelemetry)
- [ ] **v2.0**: Multi-tenant support with authentication

---

## 🤝 Contributing

We welcome contributions! Here's how to get started:

1. **Fork the repository**
2. **Create a feature branch**: `git checkout -b feature/amazing-feature`
3. **Make your changes** and add tests
4. **Run tests**: `pytest tests/ -v`
5. **Commit**: `git commit -m 'Add amazing feature'`
6. **Push**: `git push origin feature/amazing-feature`
7. **Open a Pull Request**

### Contribution Guidelines

- **Code Style**: Follow PEP 8 for Python code
- **Documentation**: Update README and docstrings
- **Tests**: Add tests for new features
- **Commits**: Use conventional commit messages
- **Architecture**: Maintain adapter pattern separation

---

## 📄 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 Acknowledgments

- **LangGraph** for workflow orchestration
- **llama.cpp** for efficient local LLM inference
- **Serper** for web search API
- **Qwen Team** for the open-source model

---

## 📞 Support

- **Documentation**: See `ARCHITECTURE.md` and `UI_SERVICE_SETUP.md`
- **Issues**: [GitHub Issues](https://github.com/sertannavdann/gRPC_LLM_Container/issues)
- **Discussions**: [GitHub Discussions](https://github.com/sertannavdann/gRPC_LLM_Container/discussions)

---

**Built with ❤️ using LangGraph, gRPC, and modern Python**
