# Architecture Overview

**Last Updated**: February 2026
**Status**: Current Implementation State (not aspirational)

## Table of Contents
1. [System Overview](#system-overview)
2. [Service Catalog](#service-catalog)
3. [Core Components](#core-components)
4. [Data Flow](#data-flow)
5. [Module System Architecture](#module-system-architecture)
6. [Observability Stack](#observability-stack)
7. [Design Decisions](#design-decisions)
8. [Implementation Status](#implementation-status)

---

## System Overview

The gRPC LLM Agent Framework (NEXUS) is a self-evolving agent system built on:
- **Unified Orchestrator**: Single coordination service (replaced supervisor-worker mesh)
- **LIDM**: Language-Integrated Decision Making for dynamic routing
- **Module System**: Self-evolving adapter infrastructure
- **Context Bridge**: HTTP-based dashboard ↔ orchestrator communication
- **Observability**: Prometheus, Grafana, cAdvisor stack

### High-Level Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        User Interface                        │
│                    (Next.js on :5001)                        │
└────────────┬──────────────────────────────────┬─────────────┘
             │                                   │
     ┌───────▼────────┐                  ┌──────▼──────────┐
     │  Dashboard API │                  │   Pipeline UI   │
     │    (:8001)     │◄─────SSE─────────│  (React Flow)   │
     └───────┬────────┘                  └─────────────────┘
             │
     ┌───────▼────────────────────────────────────────────────┐
     │           Context Bridge (HTTP)                        │
     │  Dashboard ◄──► Orchestrator ◄──► LLM Service         │
     └────────────────────────────────────────────────────────┘
                              │
              ┌───────────────┼───────────────┐
              │               │               │
      ┌───────▼───────┐ ┌────▼─────┐ ┌──────▼──────┐
      │  ChromaDB RAG │ │ Sandbox  │ │  Admin API  │
      │    (:50052)   │ │ (:50057) │ │   (:8003)   │
      └───────────────┘ └──────────┘ └─────────────┘
                              │
                     ┌────────▼────────┐
                     │  Module System  │
                     │ (Loader/Registry│
                     │  /Credentials)  │
                     └─────────────────┘
```

---

## Service Catalog

### Core Services

| Service | Port | Purpose | Health Check |
|---------|------|---------|--------------|
| **Orchestrator** | 50054 (gRPC) | Task execution, LIDM routing, tool calling | `curl http://localhost:8003/admin/health` |
| **Dashboard** | 8001 (HTTP) | Context aggregation, adapter management | `curl http://localhost:8001/health` |
| **UI Service** | 5001 (HTTP) | Next.js frontend, Pipeline visualization | `curl http://localhost:5001` |
| **LLM Service** | 50051 (gRPC) | Model inference (llama.cpp) | gRPC healthcheck |
| **Chroma Service** | 50052 (gRPC) | Vector DB for RAG | gRPC healthcheck |
| **Sandbox Service** | 50057 (gRPC) | Isolated code execution | gRPC healthcheck |
| **Admin API** | 8003 (HTTP) | Module CRUD, config management | `curl http://localhost:8003/admin/system-info` |

### Observability Services

| Service | Port | Purpose | Access |
|---------|------|---------|--------|
| **Prometheus** | 9090 | Metrics collection | http://localhost:9090 |
| **Grafana** | 3000 | Dashboards & alerts | http://localhost:3000 (admin/admin) |
| **cAdvisor** | 8080 | Container metrics | http://localhost:8080 |

---

## Core Components

### 1. Unified Orchestrator

**Location**: `orchestrator/orchestrator_service.py`

**Replaced**: Previous supervisor-worker mesh architecture (deprecated in Feb 2026)

**Responsibilities**:
- Task execution lifecycle management
- LIDM-based routing (complexity classification)
- Tool calling and result synthesis
- Context bridge HTTP client
- Module loader/registry/credential store integration

**Key Classes**:
- `OrchestratorService`: Main gRPC service
- `DelegationManager`: LIDM tier classification
- `LLMClientPool`: Multi-tier model management
- `ContextBridge`: HTTP client for dashboard context

**LIDM Tiers**:
- **Standard**: Simple queries (qwen2.5-0.5b)
- **Heavy**: Complex reasoning (Qwen2.5-14B, Mistral-Small-24B)
- **Ultra**: Reserved for future multi-model orchestration

### 2. LIDM (Language-Integrated Decision Making)

**Philosophy**: Use a small LLM to classify task complexity, then route to appropriate tier.

**Benefits**:
- 10x faster response for simple queries
- Cost savings (smaller models for simple tasks)
- Scalable to multiple providers

**Configuration**: `config/routing_config.json`
```json
{
  "lidm_tier_models": {
    "heavy": ["Qwen2.5-14B-Instruct-Q4_K.gguf"],
    "standard": ["qwen2.5-0.5b-instruct-q5_k_m.gguf"]
  }
}
```

**Delegation Manager**: `orchestrator/delegation_manager.py`
- Prompt-based classification (200-token context window)
- Configurable thresholds
- Observer pattern for hot-reload

### 3. Module System (NEXUS Core)

**Vision**: Self-evolving agent that can build, test, and deploy modules without human intervention.

**Status (Feb 2026)**: Track A phases A1-A3 complete (infrastructure), A4 in progress (LLM-driven builder).

**Components**:

#### Module Loader
**Location**: `shared/modules/loader.py`

- `importlib.util.spec_from_file_location()` for dynamic imports
- Load/unload/reload/enable/disable operations
- Thread-safe module state management

#### Module Registry
**Location**: `shared/modules/registry.py`

- SQLite persistent store (`data/module_registry.db`)
- Survives container restarts
- Tracks: category, platform, version, status, enabled_at, disabled_at

#### Credential Store
**Location**: `shared/modules/credentials.py`

- Fernet symmetric encryption (AES-128)
- `MODULE_ENCRYPTION_KEY` env var (32-byte base64)
- Encrypted at rest (`data/module_credentials.db`)
- **Never** passed to LLM context

#### Module Manifest
**Format**: `modules/{category}/{platform}/manifest.json`

```json
{
  "name": "openweather",
  "category": "weather",
  "platform": "openweather",
  "version": "1.0.0",
  "adapter_class": "OpenWeatherAdapter",
  "adapter_file": "adapter.py",
  "required_credentials": ["api_key"],
  "description": "OpenWeather API integration"
}
```

### 4. Context Bridge

**Purpose**: HTTP-based communication between orchestrator and dashboard (replaces direct Python imports).

**Why HTTP**: Decouples services, enables independent scaling, avoids circular dependencies.

**Implementation**: `tools/builtin/context_bridge.py`

**Endpoints Used**:
- `GET /context` - Full context data
- `GET /context/summary?destination={dest}` - Formatted summaries
- `GET /context/briefing` - Daily briefing with alerts
- `GET /context/relevance` - Classified by relevance

### 5. Adapter System

**Base Class**: `shared/adapters/base.py:BaseAdapter[T]`

**Pattern**:
```python
class MyAdapter(BaseAdapter[MyDataType]):
    async def fetch_raw(self) -> Any:
        # Fetch from external API
        pass

    def transform(self, raw_data: Any) -> AdapterResult[MyDataType]:
        # Transform to canonical schema
        pass
```

**Registration**: `@register_adapter` decorator

**Categories**: `AdapterCategory` enum (finance, weather, calendar, health, navigation, gaming, social, productivity, communication, entertainment)

**Dynamic Categories**: `AdapterConfig.category` accepts `Union[AdapterCategory, str]` for module-defined categories.

---

## Data Flow

### User Query Lifecycle

```
1. User → UI Service (Next.js)
   │
2. UI → Dashboard API (/chat)
   │
3. Dashboard → Orchestrator (gRPC ExecuteTask)
   │
4. Orchestrator → LIDM Classification
   ├─ Simple → Standard Tier (0.5B model)
   └─ Complex → Heavy Tier (14B model)
   │
5. Orchestrator → Context Bridge (HTTP)
   │
6. Dashboard → Adapter Registry
   ├─ Fetch from enabled adapters
   └─ Transform to canonical schemas
   │
7. Orchestrator → Tool Execution
   ├─ Built-in tools (context, knowledge_search, calculator)
   └─ MCP bridge tools (if configured)
   │
8. Orchestrator → LLM Service (gRPC Generate)
   │
9. LLM Service → Model Inference (llama.cpp)
   │
10. Orchestrator → Result Synthesis
    │
11. Dashboard ← Response
    │
12. UI ← Formatted Response
    │
13. User ← Answer
```

### Module Installation Flow

```
1. User → Admin API (POST /admin/modules/{category}/{platform})
   │
2. Admin API → Module Loader.load()
   │
3. Module Loader → Read manifest.json
   │
4. Module Loader → Import adapter.py
   │
5. Module Loader → Module Registry (persist)
   │
6. Module Registry → SQLite INSERT
   │
7. Admin API → Dashboard /adapters refresh
   │
8. Dashboard → Adapter Registry (dynamic lookup)
   │
9. User ← Module enabled (200 OK)
```

---

## Module System Architecture

### Track A: Self-Evolution Infrastructure

**A1: Foundation** ✅ Complete (Jan 2026)
- Module manifest schema
- Module loader with importlib
- SQLite registry

**A2: Security** ✅ Complete (Jan 2026)
- Fernet credential store
- Encrypted at-rest storage
- Credential injection (not LLM-visible)

**A3: Agent Integration** ✅ Complete (Feb 2026)
- Tool registration (build_module, install_module, etc.)
- Intent patterns (build_module, manage_modules)
- Dashboard /modules endpoint

**A4: LLM Builder** 🚧 In Progress (Feb 2026)
- `build_module` tool (stub implemented)
- Template-based code generation
- Sandbox validation

### Module Directory Structure

```
modules/
├── weather/
│   └── openweather/
│       ├── manifest.json
│       ├── adapter.py
│       └── test_adapter.py
├── gaming/
│   └── clashroyale/
│       ├── manifest.json
│       ├── adapter.py
│       └── test_adapter.py
└── showroom/
    └── metrics_demo/
        ├── manifest.json
        ├── adapter.py
        └── test_adapter.py
```

### Module Lifecycle States

```
DISCOVERED → LOADED → VALIDATED → INSTALLED → ENABLED
                                              ↓
                                          DISABLED
                                              ↓
                                          UNINSTALLED
```

---

## Observability Stack

### Prometheus Metrics

**Scrape Jobs**:
- Orchestrator: `:8003/metrics/prometheus`
- Dashboard: `:8001/metrics/prometheus`
- cAdvisor: `:8080/metrics`

**Custom Metrics** (`shared/observability/metrics.py`):
- `nexus_module_builds_total` - Module build attempts
- `nexus_module_validations_total` - Validation runs
- `nexus_module_installs_total` - Successful installs
- `nexus_module_status` - Current module state (0=disabled, 1=enabled, 2=failed)
- `nexus_credential_operations_total` - Credential store/retrieve ops

### Grafana Dashboards

**NEXUS Modules Dashboard** (`config/grafana/provisioning/dashboards/json/nexus-modules.json`):
- Module status (enabled/disabled/failed)
- Build & validation rates
- Container CPU/memory/network (cAdvisor)
- LIDM delegation counts
- Provider latency

### Alert Rules

**Location**: `config/prometheus/rules/pipeline_alerts.yml`

**Alerts**:
- `ModuleValidationFailures` - >5 failures in 5min
- `ModulesInFailedState` - Any modules in failed state
- `ContainerHighCPU` - >80% CPU for 5min
- `ContainerHighMemory` - >80% memory for 5min

### Pipeline SSE Stream

**Endpoint**: `GET /stream/pipeline-state` (Dashboard service)

**Interval**: 2 seconds

**Data**:
```json
{
  "services": {
    "orchestrator": {"healthy": true, "latency_ms": 12},
    "dashboard": {"healthy": true, "latency_ms": 5},
    "llm": {"healthy": true, "latency_ms": 150},
    "chroma": {"healthy": true, "latency_ms": 8},
    "sandbox": {"healthy": true, "latency_ms": 20}
  },
  "modules": [
    {"category": "weather", "platform": "openweather", "status": "enabled"},
    {"category": "gaming", "platform": "clashroyale", "status": "enabled"}
  ],
  "pipeline_stages": ["ingest", "aggregate", "synthesize", "deliver"]
}
```

---

## Design Decisions

### Why Unified Orchestrator (vs. Supervisor-Worker Mesh)?

**Previous**: Supervisor service managed multiple worker agents, each with specialized skills.

**Problems**:
- Message passing overhead
- Complex state synchronization
- Difficult debugging
- No clear ownership of tool results

**Solution**: Single orchestrator with LIDM routing.

**Benefits**:
- Simpler reasoning (one service, one state)
- Direct tool calling (no delegation overhead)
- LIDM provides specialization without coordination cost

### Why LIDM?

**Alternative**: Route all queries to large model.

**Problem**: 10x higher latency and cost for simple queries.

**Solution**: Small model (0.5B) classifies complexity, routes to appropriate tier.

**Trade-off**: Extra 200ms for classification, but 10x speedup for 70% of queries.

### Why gRPC?

**Alternatives**: REST, GraphQL, message queues.

**Reasons**:
- Type-safe contracts (protobuf)
- Streaming support (llama.cpp streaming)
- Efficient binary serialization
- Built-in load balancing

**Trade-off**: More complex than REST, but essential for LLM streaming.

### Why Fernet Encryption?

**Alternative**: AES-256 with custom key management.

**Reasons**:
- Battle-tested (cryptography.io)
- Includes authentication (HMAC)
- Timestamp-based expiration
- Simple API (encrypt/decrypt)

**Trade-off**: Less flexible than custom, but reduces security risk.

### Why HTTP Context Bridge (vs. Direct Import)?

**Previous**: Orchestrator directly imported dashboard adapters.

**Problems**:
- Circular dependencies
- Tight coupling
- Cannot scale independently

**Solution**: HTTP API for context retrieval.

**Benefits**:
- Decoupled services
- Independent deployment
- Clear API boundary

**Trade-off**: 5-10ms HTTP overhead vs. direct function call.

---

## Implementation Status

### Track A: Self-Evolving Module Infrastructure

| Phase | Status | Completion Date |
|-------|--------|-----------------|
| A1: Foundation | ✅ Complete | Jan 2026 |
| A2: Security | ✅ Complete | Jan 2026 |
| A3: Agent Integration | ✅ Complete | Feb 2026 |
| A4: LLM Builder | 🚧 In Progress | TBD |

### Track B: Observability & Control

| Phase | Status | Completion Date |
|-------|--------|-----------------|
| B1: Metrics Foundation | ✅ Complete | Jan 2026 |
| B2: Admin API v1 | ✅ Complete | Jan 2026 |
| B3: Admin API v2 | ✅ Complete | Feb 2026 |
| B4: Pipeline UI | ✅ Complete | Feb 2026 |

### Track C: Co-Evolution (Planned)

| Phase | Status | Target Date |
|-------|--------|-------------|
| C1: Curriculum Agent | 📋 Planned | Q2 2026 |
| C2: Executor Agent | 📋 Planned | Q2 2026 |
| C3: Approval Gates | 📋 Planned | Q2 2026 |

### Real Adapter Integrations

| Adapter | Status | Credentials Required | Completion Date |
|---------|--------|----------------------|-----------------|
| OpenWeather | ✅ Complete | API key | Jan 2026 |
| Google Calendar | ✅ Complete | OAuth2 token | Jan 2026 |
| Clash Royale | ✅ Complete | API key + player tag | Jan 2026 |
| CIBC Finance | ✅ Complete | None (CSV files) | Dec 2025 |

---

## What's NOT Implemented (Yet)

See [KNOWN-ISSUES.md](./KNOWN-ISSUES.md) for technical debt.

**Major Missing Features**:
1. LLM-driven module builder (Track A4)
2. Approval gates for module installation (Track C3)
3. Multi-tenant support
4. OAuth2 authentication for API endpoints
5. Module versioning and rollback
6. Automated E2E testing for Pipeline UI
7. Module marketplace/registry

---

## References

- [PROJECT_VISION.md](./archive/PROJECT_VISION.md) - Original aspirational design
- [PLAN.md](./archive/PLAN.md) - Detailed tier 1-5 implementation roadmap
- [API-REFERENCE.md](./API-REFERENCE.md) - REST and gRPC API documentation
- [EXTENSION-GUIDE.md](./EXTENSION-GUIDE.md) - How to build modules
- [OPERATIONS.md](./OPERATIONS.md) - Monitoring and troubleshooting
