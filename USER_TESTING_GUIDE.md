# User Testing Guide - gRPC LLM Agent Framework

> **Purpose**: This document is a comprehensive guide for understanding, testing, and operating the gRPC LLM Agent Framework. It includes architecture details, port mappings, functionality overview, and testing procedures.
> **Date**: February 8, 2026
> **Version**: Cohesion Branch
> **Tester Name**: _________________________

---

## Table of Contents

1. [Getting Started](#1-getting-started)
2. [Architecture Overview](#2-architecture-overview)
3. [Service Port Map](#3-service-port-map)
4. [Functionality Set](#4-functionality-set)
5. [Make Commands Reference](#5-make-commands-reference)
6. [Feature Tests](#6-feature-tests)
   - [6.1 Chat Interface (UI Service)](#61-chat-interface-ui-service)
   - [6.2 Math & Calculations](#62-math--calculations)
   - [6.3 Code Execution (Sandbox)](#63-code-execution-sandbox)
   - [6.4 Knowledge Search (ChromaDB)](#64-knowledge-search-chromadb)
   - [6.5 Web Search](#65-web-search)
   - [6.6 Dashboard & Context](#66-dashboard--context)
   - [6.7 Finance Dashboard](#67-finance-dashboard)
   - [6.8 MCP Bridge Tools](#68-mcp-bridge-tools)
7. [Observability & Monitoring](#7-observability--monitoring)
8. [Error Handling Tests](#8-error-handling-tests)
9. [Refactoring Changelog](#9-refactoring-changelog)
10. [Overall Feedback](#10-overall-feedback)

---

## 1. Getting Started

### Prerequisites
- Docker Desktop running
- Terminal access
- Web browser

### Start All Services
```bash
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm
make up
```

### Check Service Health
```bash
make status
```

### Stop Services
```bash
make down
```

---

## 2. Architecture Overview

The gRPC LLM Agent Framework is a distributed microservices architecture designed for AI agent orchestration with tool execution capabilities.

### System Topology

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER INTERFACES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │  UI Service  │    │  Dashboard   │    │ MCP Bridge   │                   │
│  │  (Flask:5001)│    │ (FastAPI:8001)│   │ (FastAPI:8100)│                  │
│  └──────┬───────┘    └──────┬───────┘    └──────┬───────┘                   │
└─────────┼───────────────────┼───────────────────┼───────────────────────────┘
          │                   │                   │
          ▼                   ▼                   ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │                      ORCHESTRATOR (gRPC:50054)                       │    │
│  │  • Multi-tool intent analysis    • Request routing                   │    │
│  │  • Guardrails & rate limiting    • Token bucket management          │    │
│  │  • Idempotency support           • Crash recovery                   │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            BACKEND SERVICES                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                   │
│  │ LLM Service  │    │ChromaDB Svc  │    │Sandbox Service│                  │
│  │ (gRPC:50051) │    │ (gRPC:50052) │    │ (gRPC:50057)  │                  │
│  │ Multi-provider│   │ Vector store │    │ Code execution│                  │
│  └──────────────┘    └──────────────┘    └──────────────┘                   │
└─────────────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                          OBSERVABILITY STACK                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌───────────┐  │
│  │OTel Collector│    │  Prometheus  │    │   Grafana    │    │   Tempo   │  │
│  │ (4317/4318)  │    │   (9090)     │    │   (3001)     │    │  (3200)   │  │
│  │ Traces/Metrics│   │  Metrics DB  │    │ Dashboards   │    │ Traces DB │  │
│  └──────────────┘    └──────────────┘    └──────────────┘    └───────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Service Communication

| Protocol | Direction | Use Case |
|----------|-----------|----------|
| **gRPC** | Internal | Service-to-service communication (orchestrator ↔ backends) |
| **HTTP/REST** | External | User interfaces, health checks, MCP bridge |
| **OpenTelemetry** | Outbound | Traces and metrics to collectors |

---

## 3. Service Port Map

### Core Services

| Service | Container Name | gRPC Port | HTTP Port | Description |
|---------|----------------|-----------|-----------|-------------|
| **Orchestrator** | `orchestrator` | 50054 | 8890 (Jupyter) | Central agent coordination, tool routing |
| **LLM Service** | `llm_service` | 50051 | — | Multi-provider LLM gateway |
| **ChromaDB Service** | `chroma_service` | 50052 | — | Vector database for RAG |
| **Sandbox Service** | `sandbox_service` | 50057 | — | Isolated Python code execution |

### User Interfaces

| Service | Container Name | HTTP Port | Description |
|---------|----------------|-----------|-------------|
| **UI Service** | `ui_service` | 5001 | Flask web chat interface |
| **Dashboard** | `dashboard_service` | 8001, 8002 | FastAPI context aggregation + Finance UI |
| **MCP Bridge** | `bridge_service` | 8100 | Model Context Protocol server |

### Observability Stack

| Service | Container Name | Port(s) | Description |
|---------|----------------|---------|-------------|
| **OTel Collector** | `otel-collector` | 4317 (gRPC), 4318 (HTTP), 8888-8889, 13133 | Telemetry ingestion |
| **Prometheus** | `prometheus` | 9090 | Metrics storage & queries |
| **Grafana** | `grafana` | 3001 | Visualization dashboards |
| **Tempo** | `tempo` | 3200, 4319 | Distributed tracing backend |

### Quick Access URLs

| Resource | URL | Credentials |
|----------|-----|-------------|
| Chat Interface | http://localhost:5001 | — |
| Dashboard API | http://localhost:8001/docs | — |
| Finance Dashboard | http://localhost:8001/static/index.html | — |
| MCP Bridge | http://localhost:8100/tools | — |
| Grafana | http://localhost:3001 | admin / admin |
| Prometheus | http://localhost:9090 | — |

---

## 4. Functionality Set

### 4.1 Tool Categories

| Category | Tools | Description |
|----------|-------|-------------|
| **Math** | `math_solver` | Expression evaluation, calculations |
| **Code Execution** | `execute_code` | Sandboxed Python execution |
| **Knowledge** | `search_knowledge` | ChromaDB vector similarity search |
| **Web** | `web_search` | External web search (Serper API) |
| **User Context** | `get_commute_time`, `get_calendar` | Personal context tools |
| **Finance** | `CIBC CSV Adapter` | Bank transaction categorization |

### 4.2 LLM Providers

| Provider | Model(s) | Switch Command |
|----------|----------|----------------|
| **Local** | qwen2.5-3b-instruct | `make provider-local` |
| **Perplexity** | sonar-pro | `make provider-perplexity` |
| **OpenAI** | gpt-4o-mini | `make provider-openai` |
| **Anthropic** | claude-3-5-sonnet | `make provider-anthropic` |
| **OpenClaw** | gpt-5.2 | `make provider-openclaw` |

### 4.3 Key Features

| Feature | Description | Related Commits |
|---------|-------------|-----------------|
| **Multi-Tool Intent** | Analyze queries requiring multiple tools | `de1f727` |
| **Token Bucket Rate Limiting** | Provider-level request throttling | `aae9582` |
| **Idempotency Support** | Safe tool retries without duplicates | `27c5784` |
| **Finance Dashboard** | Transaction visualization with categorization | `620f3b1`, `1967d9d` |
| **Tool Selection Evals** | Framework for evaluating tool routing | `9df08ec` |
| **Crash Recovery** | Realistic service restart handling | `eaa8a9c` |

---

## 5. Make Commands Reference

### 🚀 Quick Start Commands

```bash
make start              # Build and start all services
make dev                # Start backend + UI in dev mode
make stop               # Stop all services
make status             # Show service status and health
```

### 🔧 Service Management

```bash
make up                 # Start all services (detached)
make down               # Stop and remove containers
make restart            # Restart all services
make restart-<svc>      # Restart specific service (e.g., make restart-orchestrator)
```

### 📊 Logging & Monitoring (Verbose)

```bash
# Full service logs
make logs               # Follow ALL service logs
make logs-<svc>         # Follow specific service (e.g., make logs-orchestrator)
make logs-tail          # Tail all logs with limited history (50 lines)

# Specific log targets
make logs-orch          # Orchestrator logs (100 lines tail)
make logs-bridge        # MCP Bridge service logs
make logs-grafana       # Grafana logs
make logs-prometheus    # Prometheus logs
make logs-otel          # OpenTelemetry Collector logs

# Filtered logging
make watch-orchestrator # Watch orchestrator with grep filter (Tool|ERROR|WARNING)
```

### 🏗️ Build Commands

```bash
make build              # Build all containers (parallel)
make build-<svc>        # Build specific service
make build-clean        # Full rebuild without cache
make rebuild            # Clean build + restart
make rebuild-orchestrator  # Force rebuild orchestrator (no cache)
make rebuild-all        # Force rebuild all services (no cache)
```

### 🤖 LLM Provider Management

```bash
make provider-status    # Show current provider config
make provider-local     # Use local LLM (llama.cpp)
make provider-perplexity # Use Perplexity Sonar API
make provider-openai    # Use OpenAI GPT API
make provider-anthropic # Use Anthropic Claude API
make provider-openclaw  # Use OpenClaw Gateway (gpt-5.x)
make set-model MODEL=<name>  # Set custom model
```

### 💬 Chat & Query

```bash
make query Q="..."      # Send query to agent
make chat               # Interactive chat mode
make tool-test          # Test tool calling with sample query
make smoke-test         # Run multiple test queries
```

### 🔗 MCP Bridge Commands

```bash
make bridge-up          # Start MCP bridge service
make bridge-down        # Stop bridge service
make bridge-health      # Check bridge service health
make bridge-tools       # List tools exposed via MCP
make bridge-query Q="..." # Test query through bridge
make bridge-briefing    # Get daily briefing via bridge
make openclaw-setup     # Full bidirectional setup
```

### 📊 Health & Status

```bash
make health             # Check all service health (gRPC)
make health-all         # Enhanced health view (Docker status)
make health-watch       # Auto-refresh health every 5s
make ps                 # Show running containers
make stats              # Show container resource usage
make verify-code        # Verify code is current in container
```

### 📊 Observability Stack

```bash
make observability-up   # Start Prometheus, Grafana, OTel Collector
make observability-down # Stop observability stack
make observability-health # Check observability services health
make open-grafana       # Open Grafana in browser (localhost:3001)
make open-prometheus    # Open Prometheus in browser (localhost:9090)
```

### 🧪 Testing

```bash
make test               # Run all tests
make test-unit          # Run unit tests only
make test-integration   # Run integration tests
make test-e2e           # Run end-to-end tests
make test-tools         # Run tool tests
```

### 📦 Proto Generation

```bash
make proto-gen          # Generate all protobuf stubs
make proto-gen-shared   # Generate shared stubs only
```

### 🗄️ Database Management

```bash
make db-reset           # Reset all databases
make db-backup          # Backup databases
make db-restore BACKUP=<dir> # Restore from backup
```

### 🧹 Cleanup

```bash
make clean              # Remove generated files
make clean-docker       # Clean Docker resources (volumes, orphans)
make clean-ui           # Clean UI build artifacts
make clean-all          # Full cleanup (volumes, images)
make clean-logs         # Clear log files
```

### ⚡ Short Aliases

```bash
make r                  # restart
make l                  # logs
make s                  # status
make h                  # health
make b                  # build
make u                  # up
make d                  # down
make q                  # query
make c                  # chat
```

---

---

## 6. Feature Tests

### 6.1 Chat Interface (UI Service)

**URL**: http://localhost:5001

#### Test 1.1: Basic Greeting
| Field | Value |
|-------|-------|
| **Input** | "Hello, how are you?" |
| **Expected** | A friendly greeting response |
| **Actual Response** | |
| **Response Time** | _____ seconds |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 1.2: Multi-turn Conversation
| Field | Value |
|-------|-------|
| **Input 1** | "My name is Alex" |
| **Input 2** | "What is my name?" |
| **Expected** | Should remember "Alex" |
| **Actual Response** | |
| **Did it remember?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 1.3: UI Responsiveness
| Criteria | Rating (1-5) | Notes |
|----------|--------------|-------|
| Page load time | | |
| Input responsiveness | | |
| Message streaming | | |
| Mobile friendliness | | |
| Error messages clarity | | |

---

### 6.2 Math & Calculations

**Tests the math_solver tool**

#### Test 2.1: Simple Math
| Field | Value |
|-------|-------|
| **Input** | "What is 2 + 2?" |
| **Expected** | "4" in the response |
| **Actual Response** | |
| **Contains "4"?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 2.2: Complex Math
| Field | Value |
|-------|-------|
| **Input** | "Calculate 15 * 23" |
| **Expected** | "345" in the response |
| **Actual Response** | |
| **Contains "345"?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 2.3: Math Expression
| Field | Value |
|-------|-------|
| **Input** | "What is (5 + 3) * 2 - 7 / 2?" |
| **Expected** | "12.5" or equivalent |
| **Actual Response** | |
| **Correct Answer?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 2.4: Word Problem
| Field | Value |
|-------|-------|
| **Input** | "If I have 120 apples and give away 30%, how many do I have left?" |
| **Expected** | "84" in the response |
| **Actual Response** | |
| **Correct?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

---

### 6.3 Code Execution (Sandbox)

**Tests the execute_code tool via sandbox_service**

#### Test 3.1: Simple Print
| Field | Value |
|-------|-------|
| **Input** | "Execute this Python code: print('Hello World')" |
| **Expected** | Shows "Hello World" output |
| **Actual Response** | |
| **Executed correctly?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 3.2: Math Calculation in Code
| Field | Value |
|-------|-------|
| **Input** | "Run this code: x = [1, 2, 3, 4, 5]; print(sum(x))" |
| **Expected** | Output shows "15" |
| **Actual Response** | |
| **Correct output?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 3.3: Loop Execution
| Field | Value |
|-------|-------|
| **Input** | "Execute: for i in range(5): print(i * 2)" |
| **Expected** | "0 2 4 6 8" (or similar) |
| **Actual Response** | |
| **Loop executed?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 3.4: Error Handling
| Field | Value |
|-------|-------|
| **Input** | "Run this code: int('not a number')" |
| **Expected** | Should show error (ValueError) gracefully |
| **Actual Response** | |
| **Error shown clearly?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

---

### 6.4 Knowledge Search (ChromaDB)

**Tests the search_knowledge tool**

#### Test 4.1: Knowledge Query
| Field | Value |
|-------|-------|
| **Input** | "Search the knowledge base for information about Python" |
| **Expected** | Returns relevant results from ChromaDB |
| **Actual Response** | |
| **Found results?** | Yes / No |
| **Results relevant?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 4.2: Empty Results Handling
| Field | Value |
|-------|-------|
| **Input** | "Search for xyzzy123nonsense" |
| **Expected** | Should handle no results gracefully |
| **Actual Response** | |
| **Handled gracefully?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

---

### 6.5 Web Search

**Tests the web_search tool (requires SERPER_API_KEY)**

#### Test 5.1: Web Search
| Field | Value |
|-------|-------|
| **Input** | "Search the web for Python 3.12 new features" |
| **Expected** | Returns web search results |
| **Actual Response** | |
| **Search executed?** | Yes / No |
| **Results useful?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

---

### 6.6 Dashboard & Context

**URL**: http://localhost:8001

#### Test 6.1: Dashboard Health
| Field | Value |
|-------|-------|
| **URL** | http://localhost:8001/health |
| **Expected** | `{"status": "healthy"}` |
| **Actual Response** | |
| **Working?** | Yes / No |

#### Test 6.2: Context Aggregation
| Field | Value |
|-------|-------|
| **URL** | http://localhost:8001/context |
| **Expected** | Returns aggregated context JSON |
| **Actual Response** | |
| **Data returned?** | Yes / No |
| **Rating** | ⭐ ☆ ☆ ☆ ☆ (1-5) |
| **Issues/Notes** | |

#### Test 6.3: Dashboard API Docs
| Field | Value |
|-------|-------|
| **URL** | http://localhost:8001/docs |
| **Expected** | Swagger/OpenAPI documentation |
| **Working?** | Yes / No |
| **Documentation quality** | ⭐ ☆ ☆ ☆ ☆ (1-5) |

---

### 6.7 Finance Dashboard

**URL**: http://localhost:8001/static/index.html

> Note: Requires bank CSV data in `dashboard_service/Bank/` folder

#### Test 7.1: Dashboard Load
| Field | Value |
|-------|-------|
| **Page loads?** | Yes / No |
| **Charts display?** | Yes / No |
| **Data visible?** | Yes / No |
| **Load time** | _____ seconds |

#### Test 7.2: Category Chart
| Field | Value |
|-------|-------|
| **Category donut chart visible?** | Yes / No |
| **Categories correct?** | Yes / No |
| **Hover info works?** | Yes / No |

#### Test 7.3: Filtering
| Field | Value |
|-------|-------|
| **Date filter works?** | Yes / No |
| **Category filter works?** | Yes / No |
| **Account filter works?** | Yes / No |
| **Search works?** | Yes / No |

#### Test 7.4: Transaction Table
| Field | Value |
|-------|-------|
| **Table displays data?** | Yes / No |
| **Pagination works?** | Yes / No |
| **Sorting works?** | Yes / No |

#### Finance Dashboard Overall Rating
| Criteria | Rating (1-5) | Notes |
|----------|--------------|-------|
| Data accuracy | | |
| UI design | | |
| Filter functionality | | |
| Chart readability | | |
| Performance | | |

---

### 6.8 MCP Bridge Tools

**URL**: http://localhost:8100

#### Test 8.1: Bridge Health
| Field | Value |
|-------|-------|
| **URL** | http://localhost:8100/health |
| **Expected** | Health status JSON |
| **Actual Response** | |
| **Working?** | Yes / No |

#### Test 8.2: List Tools
| Field | Value |
|-------|-------|
| **URL** | http://localhost:8100/tools |
| **Expected** | List of available MCP tools |
| **Tools listed** | |
| **Working?** | Yes / No |

#### Test 8.3: Tool Invocation via curl
```bash
# Test query_agent tool
curl -X POST http://localhost:8100/invoke \
  -H "Content-Type: application/json" \
  -d '{"tool": "query_agent", "arguments": {"query": "What is 2+2?"}}'
```
| Field | Value |
|-------|-------|
| **Response received?** | Yes / No |
| **Answer correct?** | Yes / No |
| **Response time** | _____ seconds |
| **Issues/Notes** | |

---

## 7. Observability & Monitoring

### 7.1 Grafana Dashboards

**URL**: http://localhost:3001 (default: admin/admin)

| Dashboard | Available? | Data Showing? | Notes |
|-----------|------------|---------------|-------|
| gRPC LLM Overview | Yes / No | Yes / No | |
| Provider Comparison | Yes / No | Yes / No | |
| Service Health | Yes / No | Yes / No | |

### 7.2 Prometheus Metrics

**URL**: http://localhost:9090

#### Test Metric Queries
| Query | Expected | Result |
|-------|----------|--------|
| `up` | Shows all targets | |
| `grpc_server_handled_total` | gRPC request counts | |
| `orchestrator_request_duration_seconds` | Latency histograms | |

### 7.3 Service Logs
```bash
# View orchestrator logs
make logs-orchestrator

# View all logs
make logs
```
| Log Quality | Rating (1-5) | Notes |
|-------------|--------------|-------|
| Error messages | | |
| Debug info | | |
| Request tracing | | |

---

## 8. Error Handling Tests

### Test 8.1: Empty Input
| Field | Value |
|-------|-------|
| **Input** | (empty message) |
| **Expected** | Graceful error message |
| **Actual Response** | |
| **Handled well?** | Yes / No |

### Test 8.2: Very Long Input
| Field | Value |
|-------|-------|
| **Input** | (paste 10,000+ characters) |
| **Expected** | Handles or limits gracefully |
| **Actual Response** | |
| **Handled well?** | Yes / No |

### Test 8.3: Special Characters
| Field | Value |
|-------|-------|
| **Input** | "Test <script>alert('xss')</script> injection" |
| **Expected** | Should sanitize/escape |
| **Actual Response** | |
| **Secure?** | Yes / No |

### Test 8.4: Timeout Handling
| Field | Value |
|-------|-------|
| **Input** | "Execute: import time; time.sleep(60)" |
| **Expected** | Should timeout after ~30s |
| **Actual Response** | |
| **Timeout worked?** | Yes / No |
| **Error message clear?** | Yes / No |

---

## 9. Refactoring Changelog

### Recent Commits (Cohesion Branch)

The following commits document the evolution of the framework:

| Commit | Type | Description |
|--------|------|-------------|
| `a9bedac` | chore | Update llm_service and gitignore settings |
| `5c02893` | docs | Add network documentation and make targets |
| `de1f727` | **feat** | Add multi-tool intent analysis and guardrails |
| `b0128ed` | chore | Add grpc_health_probe to all gRPC services |
| `4762021` | docs | Add branch summary and parallel execution plan |
| `2357c42` | chore | Add execution track status scripts |
| `620f3b1` | **feat** | Add finance dashboard with transaction visualization |
| `1967d9d` | **feat** | Add CIBC CSV finance adapter with transaction categorization |
| `9df08ec` | **feat** | Add tool selection evaluation framework |
| `aae9582` | **feat** | Add token bucket rate limiting for provider management |
| `27c5784` | **feat** | Add idempotency support for safe tool retries |
| `f9e9531` | test | Enforce strict assertions to expose formatting bugs |
| `60cba85` | fix | Replace multiprocessing.Queue with subprocess for Docker reliability |
| `eaa8a9c` | fix | Rewrite crash resume tests for realistic service restart behavior |
| `554ec98` | merge | Merge remote Cohesion branch - resolve requirements.txt conflict |

### Feature Highlights

#### Multi-Tool Intent Analysis (`de1f727`)
- Orchestrator now analyzes queries requiring multiple tools
- Added guardrails for request validation
- Improved tool routing accuracy

#### Finance Dashboard (`620f3b1`, `1967d9d`)
- Bank transaction visualization with Chart.js
- CIBC CSV adapter for transaction import
- Automatic categorization of transactions
- Filtering by date, category, and account

#### Token Bucket Rate Limiting (`aae9582`)
- Per-provider request throttling
- Configurable bucket size and refill rates
- Prevents API rate limit exhaustion

#### Idempotency Support (`27c5784`)
- Safe retry mechanism for tool calls
- Deduplication of repeated requests
- Crash recovery without duplicate side effects

#### Tool Selection Evals (`9df08ec`)
- Framework for measuring tool routing accuracy
- Benchmark suite for evaluating improvements
- Regression detection for tool selection

---

## 10. Overall Feedback

### 10.1 Feature Priority Assessment

Rate each feature's importance (1=Low, 5=Critical):

| Feature | Working? | Importance (1-5) | Needs Work? |
|---------|----------|------------------|-------------|
| Chat UI | Yes / No | | Yes / No |
| Math calculations | Yes / No | | Yes / No |
| Code execution | Yes / No | | Yes / No |
| Knowledge search | Yes / No | | Yes / No |
| Web search | Yes / No | | Yes / No |
| Dashboard | Yes / No | | Yes / No |
| Finance dashboard | Yes / No | | Yes / No |
| MCP Bridge | Yes / No | | Yes / No |
| Monitoring | Yes / No | | Yes / No |

### 10.2 Critical Issues Found

List any critical issues that prevent normal use:

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

### 10.3 Usability Issues

List any usability/UX issues:

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

### 10.4 Missing Features

What features would you expect but are missing?

1. _______________________________________________
2. _______________________________________________
3. _______________________________________________

### 10.5 Performance Issues

| Issue | Severity (1-5) | Description |
|-------|----------------|-------------|
| | | |
| | | |
| | | |

### 10.6 Suggestions for Improvement

**Top 3 improvements you'd recommend:**

1. _______________________________________________

2. _______________________________________________

3. _______________________________________________

### 10.7 Overall Rating

| Category | Rating (1-5) |
|----------|--------------|
| Functionality | ⭐ ☆ ☆ ☆ ☆ |
| Reliability | ⭐ ☆ ☆ ☆ ☆ |
| Performance | ⭐ ☆ ☆ ☆ ☆ |
| Usability | ⭐ ☆ ☆ ☆ ☆ |
| Documentation | ⭐ ☆ ☆ ☆ ☆ |
| **Overall** | ⭐ ☆ ☆ ☆ ☆ |

### 10.8 Additional Comments

```
(Write any additional feedback here)





```

---

## Quick Reference Commands

```bash
# Start all services
make up

# Check status
make status

# View logs
make logs                    # All services
make logs-orchestrator      # Orchestrator only
docker logs llm_service     # Specific service

# Restart a service
make restart-orchestrator

# Stop everything
make down

# Run tests
make test-integration

# Health check via terminal
curl http://localhost:8001/health
curl http://localhost:8100/health
```

---

**Thank you for testing! Your feedback helps improve this project.**

*Please save this file and send it to the development team when complete.*
