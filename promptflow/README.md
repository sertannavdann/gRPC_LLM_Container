# Prompt Flow Integration

This directory contains Microsoft Prompt Flow configurations for visual workflow editing, evaluation, and prompt management.

## 📁 Directory Structure

```
promptflow/
├── connections/          # LLM provider connection configs
│   ├── local_llm.yaml   # Local llama.cpp via gRPC
│   ├── openai.yaml      # OpenAI GPT models
│   ├── anthropic.yaml   # Anthropic Claude models
│   └── perplexity.yaml  # Perplexity Sonar models
├── flows/
│   ├── agent_workflow/  # Main agent DAG workflow
│   │   ├── flow.dag.yaml
│   │   ├── intent_analyzer.py
│   │   ├── context_retriever.py
│   │   ├── tool_selector.jinja2
│   │   ├── tool_executor.py
│   │   └── synthesize_response.jinja2
│   └── evaluator/       # Evaluation workflow
│       ├── flow.dag.yaml
│       ├── run_agent.py
│       ├── evaluate_tools.py
│       └── evaluate_answer.py
├── data/
│   └── eval_cases.csv   # Test cases for batch evaluation
├── prompts/
│   ├── agent_system.yaml     # System prompts with variants
│   └── tool_selection.yaml   # Tool selection prompts
└── README.md
```

## 🚀 Quick Start

### 1. Install Prompt Flow

```bash
pip install promptflow promptflow-tools promptflow-devkit
```

### 2. Set Up Connections (VS Code)

1. Open VS Code with Prompt Flow extension
2. Go to **Prompt Flow** sidebar (icon looks like a flow chart)
3. Click **Connections** → **+** to add a connection
4. Select connection type (OpenAI, Anthropic, Custom) and configure

### 3. Set Up Connections (CLI)

```bash
# Set API keys as environment variables first
export OPENAI_API_KEY="your-key"
export ANTHROPIC_API_KEY="your-key"

# Create connections
make pf-connection-openai
make pf-connection-anthropic
```

### 4. Run the Agent Workflow

```bash
# Test with a query
make pf-run Q="What is 25 * 17?"

# With debug output
make pf-run-debug Q="Calculate the square root of 144"
```

### 5. Run Batch Evaluation

```bash
make pf-eval
```

## 🔧 Makefile Commands

| Command | Description |
|---------|-------------|
| `make pf-run Q="..."` | Run agent workflow with query |
| `make pf-run-debug Q="..."` | Run with debug output |
| `make pf-eval` | Run batch evaluation |
| `make pf-serve` | Serve flow as API (port 8080) |
| `make pf-trace` | Start trace UI (port 23333) |
| `make pf-connections` | List registered connections |
| `make pf-build` | Build Docker package |

## 📐 Agent Workflow

The agent workflow is a 5-node DAG that mirrors the orchestrator logic:

```
┌──────────────────┐
│   user_query     │ (Input)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│ intent_analyzer  │ Pattern matching for tool detection
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│context_retriever │ ChromaDB semantic search
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  tool_selector   │ LLM-based tool selection (Jinja2)
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│  tool_executor   │ gRPC tool execution
└────────┬─────────┘
         │
         ▼
┌──────────────────┐
│synthesize_response│ Final response generation (Jinja2)
└──────────────────┘
```

## 📊 Evaluation Framework

### Test Cases (`data/eval_cases.csv`)

| Field | Description |
|-------|-------------|
| `query` | User input query |
| `expected_tools` | Comma-separated expected tool names |
| `expected_answer_contains` | Keywords that should appear in answer |
| `category` | Test category (math, code, search, conversation) |

### Evaluation Metrics

- **Tool Precision**: % of selected tools that were correct
- **Tool Recall**: % of expected tools that were selected
- **Tool F1**: Harmonic mean of precision and recall
- **Answer Match**: Whether expected keywords appear in answer

## 🔄 A/B Testing Prompts

### System Prompt Variants (`prompts/agent_system.yaml`)

| Variant | Description |
|---------|-------------|
| `concise` | Brief, focused responses |
| `detailed` | Comprehensive explanations |
| `professional` | Formal, business-oriented tone |

### Usage in Flow

```yaml
# In flow.dag.yaml, reference variants:
inputs:
  prompt_variant:
    type: string
    default: "concise"
```

## 🔌 Connection Types

### Local LLM (gRPC)

```yaml
name: local_llm
type: custom
module: llm_service.grpc_client
configs:
  host: localhost
  port: 50051
```

### OpenAI

```yaml
name: openai_connection
type: open_ai
api_key: ${env:OPENAI_API_KEY}
api_base: https://api.openai.com/v1
```

### Anthropic

```yaml
name: anthropic_connection
type: custom
configs:
  api_key: ${env:ANTHROPIC_API_KEY}
  model: claude-sonnet-4-20250514
```

## 🐳 Serving as Docker

```bash
# Build Docker image
make pf-build

# Run the container
docker run -p 8080:8080 agent-workflow:latest
```

## 📡 API Endpoints (when served)

When running `make pf-serve`:

```bash
# Health check
curl http://localhost:8080/health

# Run flow
curl -X POST http://localhost:8080/score \
  -H "Content-Type: application/json" \
  -d '{"user_query": "What is 5 + 3?", "debug_mode": false}'
```

## 🔍 Tracing & Debugging

### Start Trace UI

```bash
make pf-trace
# Open http://localhost:23333
```

### View Traces in VS Code

1. Open Prompt Flow sidebar
2. Click **Trace Collections**
3. Select a trace to view execution details

## 🎯 Best Practices

1. **Version prompts**: Use `prompts/` directory for all prompt templates
2. **Test changes**: Run `make pf-eval` before deploying changes
3. **Use variants**: A/B test prompts with the variants system
4. **Monitor traces**: Check trace UI for performance issues
5. **Batch test**: Use `data/eval_cases.csv` for regression testing
