# User Testing Guide - gRPC LLM Agent Framework

> **Purpose**: This document is a comprehensive guide for understanding, testing, and operating the gRPC LLM Agent Framework. It includes architecture details, port mappings, functionality overview, and testing procedures.
> **Date**: February 8, 2026
> **Version**: Cohesion Branch
> **Tester Name**: _________________________

---

## Table of Contents

1. [Getting Started](#1-getting-started)
   - [Docker Rebuild Guidance](#-docker-rebuild-guidance)
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
   - [6.9 Weather Integration](#69-weather-integration)
   - [6.10 Gaming Integration](#610-gaming-integration)
   - [6.11 Integrations Configuration Page](#611-integrations-configuration-page)
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

### 🐳 Docker Rebuild Guidance

> **Key rule**: Docker images are snapshots. If you change code on disk the running containers still have the _old_ code until you rebuild.

#### When do I need to rebuild?

| What changed? | Rebuild needed? | Command |
|---------------|-----------------|--------|
| Python source in a service folder (e.g. `orchestrator/*.py`) | **Yes** — image must be rebuilt | `make quick-orchestrator` |
| `requirements.txt` / new pip dependency | **Yes** — layer with `pip install` is cached | `make rebuild-orchestrator` (no-cache) |
| `Dockerfile` itself | **Yes** | `make rebuild-orchestrator` |
| `docker-compose.yaml` env vars or ports only | **No** — recreate is enough | `make restart-orchestrator` |
| Config files mounted as volumes (`.env`, `otel-collector-config.yaml`, Grafana provisioning) | **No** — changes are live | Restart the service: `make restart-grafana` |
| Next.js / UI code (`ui_service/src/**`) | **Yes** — built inside container | `make quick-ui_service` |
| Proto files (`shared/proto/`) | **Yes** — regenerate + rebuild consumers | `make proto-gen && make rebuild-all` |
| Multiple services touched | **Yes** | `make rebuild-all` |

#### Rebuild cheat-sheet

```bash
# ── Single service (fast — uses Docker cache) ──────────────
make quick-orchestrator          # build + restart orchestrator
make quick-dashboard             # build + restart dashboard_service
make quick-ui_service             # build + restart UI

# ── Single service (no cache — use when deps changed) ──────
make rebuild-orchestrator         # rmi old image → build --no-cache → recreate

# ── Everything ─────────────────────────────────────────────
make build                        # parallel build all (uses cache)
make rebuild-all                  # no-cache build all → force-recreate
make rebuild                      # alias: build-clean + restart

# ── Nuclear option (remove images + volumes) ───────────────
make clean-docker                 # prune containers, images, volumes
make start                        # build + up + status (fresh start)
```

#### After pulling new code / switching branches

```bash
git pull                          # or: git checkout <branch>
make rebuild-all                  # full no-cache rebuild
make status                       # verify all services are healthy
```

#### Verify your code is inside the container

```bash
make verify-code                  # prints orchestrator code version
make shell-orchestrator           # open a shell, inspect files manually
```

#### Troubleshooting containers

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Service shows **Exited (1)** | Crash on startup — check logs | `make logs-<svc>` then fix + `make quick-<svc>` |
| Code changes not reflected | Docker cache served old layer | `make rebuild-<svc>` (no-cache) |
| "Module not found" error | Stale image missing new pip dep | `make rebuild-all` |
| Port already in use | Old container lingering | `make down && make up` |
| Grafana dashboards empty | Provisioning not mounted | `make restart-grafana` |
| UI stuck on old version | Next.js built into image | `make quick-ui_service` |
| `.env` changes not picked up | Env file is volume-mounted | `make restart` (no rebuild needed) |
| All services unhealthy | Docker Desktop restarted | `make down && make start` |

#### Service dependency order

Docker Compose handles `depends_on` automatically, but if you're restarting manually:

```
1. otel-collector, prometheus, tempo, grafana   (observability — no deps)
2. llm_service, chroma_service, sandbox_service (backends — no deps)
3. orchestrator                                 (depends on backends)
4. dashboard_service (dashboard)                (depends on orchestrator)
5. bridge_service                               (depends on orchestrator)
6. ui_service                                   (depends on orchestrator + dashboard)
```

> **Tip**: `make start` does `build → up → status` in the right order. Use it when in doubt.

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
| **Landing Page** | http://localhost:5001 | — |
| Chat Interface | http://localhost:5001/chat | — |
| Dashboard (Next.js) | http://localhost:5001/dashboard | — |
| Finance (embedded) | http://localhost:5001/finance | — |
| Integrations | http://localhost:5001/integrations | — |
| Monitoring (Grafana embed) | http://localhost:5001/monitoring | — |
| Dashboard API | http://localhost:8001/docs | — |
| Finance Dashboard (standalone) | http://localhost:8001 | — |
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
make status             # Beautified service status (containers, gRPC health, LLM provider)
```

### 📊 Status Commands (No Overlap)

| Command | Purpose |
|---------|---------|
| `make status` | Box-drawn overview: container health ● / ○, gRPC probes, LLM provider |
| `make status-verbose` | Everything in `status` **plus** port map table, resource usage, Docker images |
| `make status-guide` | Per-component testing guide — how to curl / test each service individually |
| `make status-<service> log` | Tail the last 100 lines of a single service, e.g. `make status-orchestrator log` |

### 🔧 Service Management

```bash
make up                 # Start all services (detached)
make down               # Stop and remove containers
make restart            # Restart all services
make restart-<svc>      # Restart specific service (e.g., make restart-orchestrator)
```

### 📊 Logging (slog128 Rolling Window)

```bash
make logs               # Stream all logs to logs/services.log with 128 KB rolling window
make logs-dump          # Print the current slog128 buffer to stdout
make logs-clear         # Clear the rolling log file
make logs-<svc>         # Follow specific service (e.g., make logs-orchestrator)
```

> **slog128**: The `make logs` command writes timestamped logs to `logs/services.log`,
> automatically truncating to the most recent 128 KB so disk usage stays bounded.

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

**URL**: http://localhost:5001/chat

> The UI now has a **landing page** at `/` with navigation to Chat, Dashboard, Finance, and Monitoring pages.

#### Test 1.0: Landing Page & Navigation (NEW)
| Field | Value |
|-------|-------|
| **Landing page at `/` loads?** | Yes / No |
| **4 page cards visible (Chat, Dashboard, Finance, Monitoring)?** | Yes / No |
| **Navbar visible at top?** | Yes / No |
| **Click "AI Chat" → goes to `/chat`?** | Yes / No |
| **Click "Dashboard" → goes to `/dashboard`?** | Yes / No |
| **Click "Finance" → goes to `/finance`?** | Yes / No |
| **Click "Monitoring" → goes to `/monitoring`?** | Yes / No |
| **Active page is highlighted in navbar?** | Yes / No |

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

**URL**: http://localhost:8001 (also embedded at http://localhost:5001/finance)

> Bank CSV data should be in `dashboard_service/Bank/` folder.
> Filters now update **all 4 charts + summary cards + transaction table** simultaneously.

#### Test 7.1: Dashboard Load
| Field | Value |
|-------|-------|
| **Page loads?** | Yes / No |
| **Charts display?** | Yes / No |
| **Summary cards show real totals?** | Yes / No |
| **Load time** | _____ seconds |

#### Test 7.2: Category Chart
| Field | Value |
|-------|-------|
| **Category donut chart visible?** | Yes / No |
| **Categories correct?** | Yes / No |
| **Hover info works?** | Yes / No |

#### Test 7.3: Chart Filtering (NEW)
| Field | Value |
|-------|-------|
| **Select a category → charts update?** | Yes / No |
| **Select a date range → monthly chart updates?** | Yes / No |
| **Type a search term → top companies chart updates?** | Yes / No |
| **Reset → all charts return to full data?** | Yes / No |

#### Test 7.4: Transaction Table
| Field | Value |
|-------|-------|
| **Table displays data?** | Yes / No |
| **Pagination works?** | Yes / No |
| **Sorting works (click column headers)?** | Yes / No |

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

### 6.9 Weather Integration

**Requires**: `OPENWEATHER_API_KEY` in `.env`

> Real weather data is fetched from OpenWeather API and displayed in the dashboard weather widget.
> The agent can also answer weather queries via `get_user_context(categories=["weather"])`.

#### Test 9.1: Weather Widget (Dashboard)
| Field | Value |
|-------|-------|
| **URL** | http://localhost:5001/dashboard |
| **Weather widget visible?** | Yes / No |
| **Shows current temperature?** | Yes / No |
| **Shows condition (clear/clouds/rain)?** | Yes / No |
| **Shows humidity, wind, visibility stats?** | Yes / No |
| **Forecast section displays?** | Yes / No |
| **Issues/Notes** | |

#### Test 9.2: Weather Context via API
```bash
curl http://localhost:8001/context/weather | jq
```
| Field | Value |
|-------|-------|
| **Returns weather data?** | Yes / No |
| **Current conditions populated?** | Yes / No |
| **Forecasts array has entries?** | Yes / No |
| **Platform shows "openweather"?** | Yes / No |

#### Test 9.3: Weather via Agent Chat
| Field | Value |
|-------|-------|
| **Query** | "What's the weather like right now?" |
| **Agent calls get_user_context?** | Yes / No |
| **Response includes temperature?** | Yes / No |
| **Response includes conditions?** | Yes / No |
| **Response includes forecast?** | Yes / No |

#### Test 9.4: Weather Alerts
| Field | Value |
|-------|-------|
| **Extreme temp triggers alert?** | Yes / No (test with mock < -20°C or > 35°C) |
| **Precipitation alert works?** | Yes / No |
| **Alert shows in dashboard high-priority?** | Yes / No |

---

### 6.10 Gaming Integration

**Requires**: `CLASH_ROYALE_API_KEY` and `CLASH_ROYALE_PLAYER_TAG` in `.env`

> Clash Royale player stats and battle history displayed in the gaming widget.

#### Test 10.1: Gaming Widget (Dashboard)
| Field | Value |
|-------|-------|
| **URL** | http://localhost:5001/dashboard |
| **Gaming widget visible?** | Yes / No |
| **Shows player name and trophies?** | Yes / No |
| **Shows win/loss/win rate stats?** | Yes / No |
| **Shows clan name?** | Yes / No |
| **Recent battles listed?** | Yes / No |
| **Trophy changes color-coded (+green/-red)?** | Yes / No |

#### Test 10.2: Gaming Context via API
```bash
curl http://localhost:8001/context/gaming | jq
```
| Field | Value |
|-------|-------|
| **Returns gaming profile?** | Yes / No |
| **Trophies, wins, losses populated?** | Yes / No |
| **Recent battles in metadata?** | Yes / No |
| **Platform shows "clashroyale"?** | Yes / No |

#### Test 10.3: Gaming via Agent Chat
| Field | Value |
|-------|-------|
| **Query** | "How are my Clash Royale stats looking?" |
| **Agent retrieves gaming context?** | Yes / No |
| **Response mentions trophies?** | Yes / No |
| **Response mentions win rate?** | Yes / No |

---

### 6.11 Integrations Configuration Page

**URL**: http://localhost:5001/integrations

> Allows connecting/disconnecting external services via API key configuration.
> Credentials are stored in `.env` file and read at runtime.

#### Test 11.1: Page Load
| Field | Value |
|-------|-------|
| **Page loads?** | Yes / No |
| **Shows "External Services" section?** | Yes / No |
| **Shows "Built-in Sources" section?** | Yes / No |
| **Active count badge correct?** | Yes / No |
| **Navigation bar has "Integrations" link?** | Yes / No |

#### Test 11.2: OpenWeather Connection
| Field | Value |
|-------|-------|
| **Expand OpenWeather card** | Click to expand |
| **Shows API Key and City fields?** | Yes / No |
| **Enter API key → click "Connect"** | |
| **Success message appears?** | Yes / No |
| **Card shows "Connected" status?** | Yes / No |
| **Dashboard weather widget populates?** | Yes / No (after refresh) |

#### Test 11.3: Clash Royale Connection
| Field | Value |
|-------|-------|
| **Expand Clash Royale card** | Click to expand |
| **Shows API Key and Player Tag fields?** | Yes / No |
| **Enter credentials → click "Connect"** | |
| **Success message appears?** | Yes / No |
| **Dashboard gaming widget populates?** | Yes / No (after refresh) |

#### Test 11.4: Google Calendar Connection
| Field | Value |
|-------|-------|
| **Expand Google Calendar card** | Click to expand |
| **Shows Client ID, Secret, Access Token, Refresh Token fields?** | Yes / No |
| **Security notice about local storage visible?** | Yes / No |
| **Password fields toggle visibility (eye icon)?** | Yes / No |

#### Test 11.5: Disconnect Adapter
| Field | Value |
|-------|-------|
| **Click "Disconnect" on connected adapter** | |
| **Adapter status changes to "Not connected"?** | Yes / No |
| **Credentials removed from .env?** | Yes / No |

#### Test 11.6: Built-in Sources Display
| Field | Value |
|-------|-------|
| **CIBC shows as always active?** | Yes / No |
| **Mock adapters show as active?** | Yes / No |
| **No connect/disconnect buttons for built-in?** | Yes / No |

#### Integrations Page Overall Rating
| Criteria | Rating (1-5) | Notes |
|----------|--------------|-------|
| Ease of setup | | |
| UI clarity | | |
| Error handling | | |
| Security (credential display) | | |

---

## 7. Observability & Monitoring

### 7.1 Grafana Setup & Dashboards

**URL**: http://localhost:3001 (default: `admin` / `admin`)

#### How it works
Grafana is **auto-provisioned** — when the container starts, four JSON dashboards are loaded from
`config/grafana/provisioning/dashboards/json/` into the **gRPC LLM** folder. No manual import needed.

| Dashboard | UID | What it shows |
|-----------|-----|---------------|
| **gRPC LLM Overview** | `grpc-llm-overview` | Request rate, latency, error rate across all services |
| **Service Health** | `service-health` | Per-container CPU / memory, up/down status |
| **Provider Comparison** | `provider-comparison` | Latency & token usage per LLM provider |
| **Tool Execution** | `tool-execution` | Tool call counts, durations, circuit breaker state |

#### Verify dashboards are loaded
1. Open http://localhost:3001
2. Click the hamburger menu → **Dashboards**
3. Open folder **gRPC LLM** — 4 dashboards should appear
4. If empty, restart Grafana: `docker restart grafana`

#### Datasources (auto-provisioned)
| Name | Type | Internal URL | Notes |
|------|------|-------------|-------|
| **Prometheus** | `prometheus` | `http://prometheus:9090` | Default datasource, POST method |
| **Tempo** | `tempo` | `http://tempo:3200` | Distributed tracing |

#### Grafana embedding
Grafana is configured with `GF_SECURITY_ALLOW_EMBEDDING=true` and anonymous access
so the **Monitoring** page at http://localhost:5001/monitoring can embed dashboards via iframe.

#### Create a custom dashboard
1. Click **+** → **New dashboard** → **Add visualization**
2. Select **Prometheus** datasource
3. Enter a PromQL query, e.g.: `rate(grpc_llm_request_duration_seconds_count[5m])`
4. Save to the **gRPC LLM** folder

### 7.2 Prometheus Metrics

**URL**: http://localhost:9090

#### Scrape targets
Prometheus is configured in `config/prometheus.yaml` with these jobs:

| Job | Target | Metrics exposed |
|-----|--------|-----------------|
| `otel-collector` | `otel-collector:8889` | Collected OTLP metrics (namespace `grpc_llm_`) |
| `orchestrator` | `orchestrator:8888` | Request latency, tool calls, guard trips |
| `llm_service` | `llm_service:8888` | Token usage, provider latency |
| `dashboard_service` | `dashboard_service:8001` | Bank API hits, cache stats |
| `prometheus` | `localhost:9090` | Self-monitoring |

#### Useful PromQL queries

```promql
# Service up/down (check targets page → Status → Targets)
up

# Request rate by service (last 5 min)
rate(grpc_llm_request_duration_seconds_count[5m])

# 95th percentile latency
histogram_quantile(0.95, rate(grpc_llm_request_duration_seconds_bucket[5m]))

# Tool call total by tool name
grpc_llm_tool_calls_total

# LLM token usage
grpc_llm_tokens_total
```

#### Verify targets
1. Open http://localhost:9090/targets
2. All targets should show **UP** with a green badge
3. If a target is down, check the service container is running: `make status`

### 7.3 OpenTelemetry Collector

The OTel Collector receives OTLP gRPC (`:4317`) and HTTP (`:4318`) from all services,
then exports metrics to Prometheus and traces to Tempo.

Config file: `config/otel-collector-config.yaml`

#### Verify collector health
```bash
curl http://localhost:13133  # Health check endpoint
```

### 7.4 Monitoring via UI

The Next.js UI at http://localhost:5001/monitoring embeds Grafana in kiosk mode.
Use the tab bar to switch between Overview, Service Health, Provider Comparison, and Tool Execution dashboards.

### 7.5 Service Logs
```bash
make logs                   # Stream with 128 KB rolling window
make logs-dump              # Print current log buffer
make status-orchestrator log  # Tail specific service
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
| `1cfb228` | **feat** | Phase 7: Real adapter integrations — OpenWeather, Google Calendar, Clash Royale |
| `ae852ce` | **feat** | UI navigation, finance chart filters, real bank data, responsive layout, observability |
| `28bcf69` | docs | Add comprehensive user testing guide |
| `3b5ed39` | docs | Add Prompt Flow integration section to HLD |
| `56fa758` | build | Add Prompt Flow Makefile targets |
| `3a7ee86` | **feat** | Add Microsoft Prompt Flow integration |
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
| `554ec98` | merge | Merge remote Cohesion branch — resolve requirements.txt conflict |

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

#### UI Navigation & Landing Page (`ae852ce`)
- Persistent top navbar with active-state highlighting
- Landing page with card-based navigation to Chat, Dashboard, Finance, Monitoring
- Route pages: `/chat`, `/dashboard`, `/finance`, `/monitoring`
- Finance chart filters now update all 4 charts + summary cards + transactions
- Dashboard wired to real bank data with graceful mock fallback
- Responsive grid layout with CSS clamp for side panels
- Grafana embedded in Monitoring page with kiosk mode + dashboard tabs

#### Phase 7: Real Adapter Integrations (`1cfb228`)
- **OpenWeather** adapter — live weather data, forecasts, extreme-temp alerts
- **Clash Royale** adapter — player stats, battle history, trophy tracking
- **Google Calendar** adapter — event listing, upcoming schedule
- Canonical schemas: `WeatherData`, `GamingProfile` in `shared/schemas/canonical.py`
- Dashboard aggregator extended with weather/gaming category support
- Integrations configuration page for secure API key management

#### Prompt Flow Integration (`3a7ee86`)
- Microsoft Prompt Flow pipeline support
- Makefile targets for flow execution
- HLD documentation updated

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
| Weather integration | Yes / No | | Yes / No |
| Gaming integration | Yes / No | | Yes / No |
| Integrations page | Yes / No | | Yes / No |
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

# Check status (beautified box-drawing output)
make status

# Verbose status (ports, resources, images)
make status-verbose

# Per-component testing guide
make status-guide

# View specific service logs
make status-orchestrator log

# Stream logs with 128 KB rolling window
make logs

# Print buffered log contents
make logs-dump

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
