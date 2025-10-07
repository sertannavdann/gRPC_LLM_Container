# Distributed RAG Agent System with gRPC Orchestration

A production-grade distributed system implementing Retrieval-Augmented Generation (RAG) patterns with gRPC microservices, circuit breakers, and intelligent agent workflows. Built for scalability and reliability with LangGraph orchestration.

> **📚 Complete Documentation**: See the [docs/ directory](./docs/INDEX.md) for comprehensive guides on architecture, Apple integration, n8n workflows, and testing strategies.

## Key Features

- **Microservices Architecture**
  - Agent Orchestrator Service
  - Vector DB Service (Chroma)
  - LLM Service (Local GGUF models)
  - Tool Service (Web Search/Math)
  - Native App Intents Package (Siri/Shortcuts integrations)
  
- **Production-Ready Features**
  - Circuit breakers for tool reliability
  - Performance metrics collection
  - SQLite persistent memory
  - Health checks & reflection
  - Exponential backoff retries

- **Advanced Capabilities**
  - Streaming LLM responses
  - JSON schema validation
  - Context window management
  - Error tracking window
  - Result quality filtering

## Prerequisites

- Docker 20.10+
- Python 3.10+
- [protobuf](https://grpc.io/docs/protoc-installation/) compiler
- [grpc_health_probe](https://github.com/grpc-ecosystem/grpc-health-probe)
- SERPER_API_KEY (free tier available)

## Quick Start

```bash
# Clone repository
git clone https://github.com/yourusername/rag-agent-system.git
cd rag-agent-system

# Set up environment
## Key Features

- **Agent-centric orchestration** — the `AgentService` acts as the system denominator, arbitrating which downstream microservice (LLM, Chroma, Tool, native C++ bridge) executes next based on weighted logic and historical context.
- **Composable microservices** — independent Dockerized services for LLM inference, vector search, tool execution, and the C++ calendar bridge. Each ships with gRPC health checks, reflection, and typed clients.
- **Operational hardening** — circuit breakers, retries with backoff, persistent SQLite checkpoints, structured logging, and metrics surfaced through the orchestrator.
- **Flow-friendly design** — prompts, tool results, and context windows are normalized so visual workflow engines (e.g. n8n, Temporal, Dagster) can stitch in custom steps without bespoke glue code.

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

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **[INDEX.md](./docs/INDEX.md)** - Documentation overview and navigation guide
- **[00_OVERVIEW.md](./docs/00_OVERVIEW.md)** - System philosophy and high-level architecture
- **[01_ARCHITECTURE.md](./docs/01_ARCHITECTURE.md)** - Detailed component design and data flow
- **[02_AGENT_SERVICE.md](./docs/02_AGENT_SERVICE.md)** - Agent orchestration implementation details
- **[03_APPLE_INTEGRATION.md](./docs/03_APPLE_INTEGRATION.md)** - Native macOS/iOS integration via C++ bridge
- **[04_N8N_INTEGRATION.md](./docs/04_N8N_INTEGRATION.md)** - Workflow automation patterns and recipes
- **[05_TESTING.md](./docs/05_TESTING.md)** - Testing strategies and CI/CD setup

### Quick Links

| I want to... | See documentation |
|--------------|-------------------|
| Understand the system | [00_OVERVIEW.md](./docs/00_OVERVIEW.md) |
| Add a new tool | [02_AGENT_SERVICE.md](./docs/02_AGENT_SERVICE.md#tool-registration) |
| Integrate with Apple APIs | [03_APPLE_INTEGRATION.md](./docs/03_APPLE_INTEGRATION.md#extending-the-bridge) |
| Create an n8n workflow | [04_N8N_INTEGRATION.md](./docs/04_N8N_INTEGRATION.md#use-case-recipes) |
| Write tests | [05_TESTING.md](./docs/05_TESTING.md) |
| Deploy to production | [01_ARCHITECTURE.md](./docs/01_ARCHITECTURE.md#deployment-architecture) |

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push branch (`git push origin feature`)
5. Open Pull Request

**Documentation Contributions**: Please update relevant docs in `docs/` when adding features.

## License

Apache 2.0 - See LICENSE for details