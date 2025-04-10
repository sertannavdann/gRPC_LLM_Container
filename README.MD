# Distributed RAG Agent System with gRPC Orchestration

A production-grade distributed system implementing Retrieval-Augmented Generation (RAG) patterns with gRPC microservices, circuit breakers, and intelligent agent workflows. Built for scalability and reliability with LangGraph orchestration.

## Key Features

- **Microservices Architecture**
  - Agent Orchestrator Service
  - Vector DB Service (Chroma)
  - LLM Service (Local GGUF models)
  - Tool Service (Web Search/Math)
  
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
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

# Generate protobuf stubs
make proto-gen

# Start services (requires Docker)
make build && make up
```

## Configuration

Create .env file:
```ini
SERPER_API_KEY=your_api_key_here
LLM_MODEL_PATH=./models/qwen2.5-0.5b-instruct-q5_k_m.gguf
CONTEXT_WINDOW_SIZE=5
MAX_TOOL_RETRIES=3
```

Place GGUF model files in llm_service/models/

## Service Endpoints

| Service | Port | Health Check |
|---------|------|-------------|
| LLM Service | 50051 | `grpc_health_probe -addr:50051` |
| Chroma Service | 50052 | `grpc_health_probe -addr:50052` |
| Tool Service | 50053 | `grpc_health_probe -addr:50053` |
| Agent Service | 50054 | `grpc_health_probe -addr:50054` |

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

## Contributing

1. Fork the repository
2. Create feature branch (`git checkout -b feature`)
3. Commit changes (`git commit -am 'Add feature'`)
4. Push branch (`git push origin feature`)
5. Open Pull Request

## License

Apache 2.0 - See LICENSE for details