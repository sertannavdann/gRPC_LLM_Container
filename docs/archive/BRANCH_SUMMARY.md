# gRPC LLM Agent Framework - Branch Summary

> **Summary Document for Major Branch Change**  
> Generated: January 2025 | Updated: February 8, 2026
> Core Value: Multi-model provider management + local inference in Docker containers for agentic workflows
> Next Phase: Self-Evolving Modular Architecture (see [Planned: Self-Evolving Modules](#planned-self-evolving-modules))

---

## Executive Summary

This branch represents a **major architectural evolution** of the gRPC LLM Agent Framework, transforming it from a single-provider orchestrator into a **multi-provider agentic platform** capable of asking multiple LLM providers to solve complex problems. The changes align with emerging AI trends around:

1. **Multi-Provider Orchestration** - Runtime switching between local (llama.cpp), OpenAI, Anthropic, Perplexity, and OpenClaw
2. **Agentic Workflows** - LangGraph-based state machines with Agent0-style self-consistency scoring
3. **Observability-First Design** - Full OpenTelemetry stack with Prometheus, Grafana, and Tempo
4. **Production-Ready Containerization** - Docker Compose with health checks, crash recovery, and resource limits
5. **MCP Bridge Integration** - Model Context Protocol server bridging OpenClaw to gRPC microservices

---

## Priority Ranking by AI Trends

### 🔴 P0 - Critical (Immediate Business Value)

| Feature | Files | Impact | AI Trend Alignment |
|---------|-------|--------|-------------------|
| **Multi-Provider Registry** | `shared/providers/*` (~1200 lines) | Enables runtime provider switching | Multi-model orchestration is industry standard |
| **MCP Bridge Service** | `bridge_service/mcp_server.py` (~1032 lines) | OpenClaw integration via JSON-RPC 2.0 | MCP becoming de-facto agentic protocol |
| **Crash Recovery System** | `core/checkpointing.py` (major expansion) | WAL mode + RecoveryManager | Production reliability requirement |

### 🟡 P1 - High (Architecture Foundation)

| Feature | Files | Impact | AI Trend Alignment |
|---------|-------|--------|-------------------|
| **LangGraph State Machine** | `core/graph.py`, `core/state.py` | Agent decision loops with tool calling | Graph-based workflows replacing chains |
| **Self-Consistency Scoring** | `core/self_consistency.py` | Agent0 multi-sample verification | arXiv:2511.16043 best practices |
| **Observability Stack** | `config/grafana/`, `config/prometheus.yaml` | Full metrics/traces/dashboards | Enterprise requirement |
| **Canonical Data Schemas** | `shared/schemas/canonical.py` (~452 lines) | Platform-agnostic data structures | Adapter pattern for integrations |

### 🟢 P2 - Medium (Developer Experience)

| Feature | Files | Impact |
|---------|-------|--------|
| **Dashboard Service** | `dashboard_service/*` | Unified context aggregation |
| **UI Service Enhancements** | `ui_service/src/*` | Conversation history, settings panel |
| **JSON Parser Utility** | `shared/utils/json_parser.py` | Robust LLM output extraction |
| **Circuit Breaker** | `tools/circuit_breaker.py` | Fault tolerance for tool calls |

### ⚪ P3 - Low (Cleanup & Tests)

| Feature | Files | Impact |
|---------|-------|--------|
| Legacy Code Removal | `agent_service/*` (DELETED) | Consolidated into orchestrator |
| Test Enhancements | `tests/integration/*`, `tests/observability/*` | E2E validation |
| Documentation | `SUPERVISOR_WORKER_MESH.md`, `RUNBOOK_DOCKER.md` | Operator guides |

---

## Architectural Changes

### New Service Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           CLIENT LAYER                                   │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐                     │
│   │   UI (3000) │  │ MCP Bridge  │  │  External   │                     │
│   │   Next.js   │  │   (8100)    │  │   Clients   │                     │
│   └──────┬──────┘  └──────┬──────┘  └──────┬──────┘                     │
└──────────┼────────────────┼────────────────┼────────────────────────────┘
           │                │                │
           ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                       ORCHESTRATION LAYER                                │
│   ┌─────────────────────────────────────────────────────────────────┐   │
│   │                    Orchestrator (50054)                          │   │
│   │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │   │
│   │  │ LangGraph   │  │  Provider   │  │   Intent    │              │   │
│   │  │ StateGraph  │  │  Router     │  │   Patterns  │              │   │
│   │  └─────────────┘  └─────────────┘  └─────────────┘              │   │
│   └─────────────────────────────────────────────────────────────────┘   │
└──────────┬────────────────┬────────────────┬────────────────────────────┘
           │                │                │
           ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         PROVIDER LAYER                                   │
│   ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐   │
│   │   Local     │  │   OpenAI    │  │  Anthropic  │  │  Perplexity │   │
│   │ llama.cpp   │  │   Provider  │  │   Provider  │  │   Provider  │   │
│   │  (50051)    │  │             │  │             │  │             │   │
│   └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘   │
└─────────────────────────────────────────────────────────────────────────┘
```

### New Files Summary

| Directory | New Files | Lines Added | Purpose |
|-----------|-----------|-------------|---------|
| `shared/providers/` | 10 files | ~1,200 | Multi-provider abstraction |
| `shared/observability/` | 5 files | ~720 | OpenTelemetry integration |
| `shared/schemas/` | 2 files | ~500 | Canonical data structures |
| `bridge_service/` | 3 files | ~1,100 | MCP server implementation |
| `config/grafana/` | 6 files | ~1,500 | Dashboard provisioning |
| `tests/observability/` | 3 files | ~970 | Metrics E2E tests |
| `tests/integration/` | 5 new files | ~700 | Sandbox, self-consistency tests |

### Deleted Files

| Directory | Files Removed | Reason |
|-----------|---------------|--------|
| `agent_service/` | 4 files (~1,100 lines) | Consolidated into orchestrator |
| `shared/proto/` | `cpp_llm.proto`, `tool.proto` | Replaced with new proto definitions |

---

## OpenClaw Competitive Analysis

### Feature Comparison

| Capability | OpenClaw | This Project | Verdict |
|------------|----------|--------------|---------|
| **Provider Management** | Two-tier failover + auth rotation | Registry-based hot-swap + health checks | **Stronger** - More flexible architecture |
| **Local Inference** | Ollama integration | llama.cpp via gRPC service | **Equal** - Both containerized |
| **Workflow Engine** | Six-stage pipeline, Lane Queue | LangGraph StateGraph | **Stronger** - Graph-based more flexible |
| **Memory System** | JSONL + Markdown, hybrid search | SQLite checkpointing + crash recovery | **Stronger** - Better reliability |
| **Security** | Allowlist commands, Docker sandbox | Sandbox service with resource limits | **Equal** - Both containerized |
| **Tool System** | Skills with SKILL.md metadata | LocalToolRegistry + circuit breakers | **Stronger** - Better fault tolerance |
| **MCP Support** | Native (planned) | Bridge service (implemented) | **Implemented** vs Planned |
| **Observability** | Basic logging | Full OTEL stack (Prometheus/Grafana/Tempo) | **Significantly Stronger** |
| **Self-Consistency** | Not mentioned | Agent0-style multi-sample voting | **Unique Feature** |

### Key Differentiators

1. **Multi-Provider Agentic Flows**: Can ask multiple providers the same question and use self-consistency scoring to determine best answer
2. **Production Observability**: Full Grafana dashboards with provider comparison, tool execution metrics
3. **Crash Recovery**: Automatic resume from last checkpoint with WAL mode
4. **MCP Bridge**: Already implemented vs OpenClaw's planned support

### Overlapping Features

- Both support Docker containerization
- Both have tool/skill registries  
- Both support conversation persistence
- Both have intent classification

---

## Key Implementation Details

### Provider Registry Pattern

```python
# shared/providers/registry.py
class ProviderRegistry:
    def get_provider(self, config: ProviderConfig) -> BaseProvider:
        """Get or create provider instance with caching"""
        
    def set_default(self, name: str) -> None:
        """Set default provider for fallback"""

# Usage
registry = get_registry()
provider = registry.get_provider(anthropic_config)
response = await provider.generate(request)
```

### Self-Consistency Scoring (Agent0)

```python
# core/self_consistency.py
def compute_self_consistency(responses: List[str]) -> Tuple[float, str, int]:
    """
    Compute p̂ = proportion agreeing with majority
    Returns: (consistency_score, majority_answer, majority_count)
    """
    
class SelfConsistencyVerifier:
    def verify(self, prompt: str) -> Dict:
        """Generate k samples, compute consistency, recommend tool use if uncertain"""
```

### MCP Bridge Tools

| Tool Name | Description | Rate Limit |
|-----------|-------------|------------|
| `query_agent` | Main agent query endpoint | 10/min |
| `get_context` | Dashboard context fetch | 30/min |
| `search_knowledge` | ChromaDB vector search | 20/min |
| `execute_code` | Sandboxed code execution | 5/min |
| `get_daily_briefing` | Aggregated daily summary | 5/min |
| `plan_day` | Day planning with calendar | 5/min |
| `list_available_tools` | Tool discovery | 60/min |
| `get_service_health` | Health check (cached 30s) | 60/min |

### Grafana Dashboards

1. **gRPC LLM Overview** - Request rates, latency percentiles, error rates
2. **Provider Comparison** - Side-by-side latency, cost, success rates by provider
3. **Service Health** - Container status, resource usage, dependency health
4. **Tool Execution** - Tool call frequency, duration, error analysis

---

## Migration Guide

### For Existing Users

1. **Environment Variables**: Add provider API keys
   ```bash
   ANTHROPIC_API_KEY=...
   OPENAI_API_KEY=...
   PERPLEXITY_API_KEY=...
   LLM_PROVIDER=local  # or anthropic, openai, perplexity
   ```

2. **Docker Compose**: Use new health check targets
   ```bash
   make up              # Full stack
   make observability-up  # Observability stack
   ```

3. **Agent Service Removal**: Update any direct `agent_service` references to use `orchestrator`

### Breaking Changes

- `agent_service` directory removed - use `orchestrator` at port 50054
- Proto files reorganized - regenerate stubs if using custom clients
- Checkpoint schema updated - old checkpoints may need migration

---

## Testing Strategy

### Integration Tests Added

| Test File | Coverage |
|-----------|----------|
| `test_orchestrator_e2e.py` | Full gRPC flow, metrics, health |
| `test_sandbox_e2e.py` | Code execution, timeout, safety |
| `test_self_consistency_workflow.py` | Multi-sample generation, voting |
| `test_crash_resume.py` | Checkpoint recovery scenarios |
| `test_tool_calling.py` | Tool execution end-to-end |
| `test_metrics_e2e.py` | Prometheus metrics verification |

### Run Tests

```bash
# Unit tests
pytest tests/unit/ -v

# Integration tests (requires Docker)
make test-integration

# Observability tests
ENABLE_OBSERVABILITY=true pytest tests/observability/ -v
```

---

## Deployment Checklist

- [ ] Set all provider API keys in `.env`
- [ ] Configure `LLM_PROVIDER` for default provider
- [ ] Verify model files in `llm_service/models/`
- [ ] Run `make build-all` to rebuild images
- [ ] Start with `make up`
- [ ] Verify health at `http://localhost:8001/health`
- [ ] Check Grafana dashboards at `http://localhost:3001`
- [ ] Test MCP bridge at `http://localhost:8100/tools`

---

## Conclusion

This branch delivers a **production-ready multi-provider agentic framework** that addresses key pain points:

1. **Vendor Lock-in**: Switch providers without code changes
2. **Reliability**: Crash recovery, circuit breakers, health checks
3. **Observability**: Full metrics/traces/dashboards out of the box
4. **Extensibility**: Adapter pattern for new data sources
5. **MCP Compatibility**: Ready for OpenClaw and other MCP clients

The architecture is **significantly stronger than OpenClaw** in observability, crash recovery, and multi-provider orchestration while maintaining compatibility through the MCP bridge.

---

## Recent Commits (Feb 3-8, 2026)

```
28bcf69 docs: add comprehensive user testing guide
3b5ed39 docs(hld): add Prompt Flow integration section
56fa758 build(makefile): add Prompt Flow targets
3a7ee86 feat(promptflow): add Microsoft Prompt Flow integration
a9bedac chore: update llm_service and gitignore settings
5c02893 docs(runbook): add network documentation and make targets
de1f727 feat(orchestrator): add multi-tool intent analysis and guardrails
b0128ed chore(docker): add grpc_health_probe to all gRPC services
4762021 docs: add branch summary and parallel execution plan
2357c42 chore(scripts): add execution track status scripts
554ec98 Merge remote Cohesion branch - resolve requirements.txt conflict
8303946 chore(deps): Tier 5 - Standardize OpenTelemetry versions
48681d9 chore(cleanup): Remove registry/worker client dependencies
1ef3617 chore(cleanup): Remove unused registry and worker services
cf25897 chore: Update gitignore and local settings
```

### Diff Summary (last 5 commits)

| Files Changed | Insertions | Deletions |
|---------------|------------|-----------|
| 27 files | +2,416 | -37 |

Key changes:
- **Prompt Flow Integration**: Full Microsoft Prompt Flow workspace with agent workflow DAG, evaluator flow, connection configs, and prompt templates (17 new files)
- **User Testing Guide**: 888-line comprehensive testing document with architecture diagrams, port maps, and feature test procedures
- **High-Level Design**: Added Prompt Flow section, renumbered roadmap phases
- **Makefile**: Added Prompt Flow targets (`make pf-run`, `make pf-eval`, `make pf-serve`, `make pf-trace`)

---

## Planned: Self-Evolving Modules

> Full plan: `.claude/plans/cheerful-wibbling-eagle.md`

### Vision
Transform the framework into a **self-evolving system** where the LLM orchestrator can BUILD new modules at user request. The system generates adapter code, tests it in sandbox, gets user approval, and hot-deploys it.

### Architecture Readiness (~80%)

| Component | Status | Gap |
|-----------|--------|-----|
| `@register_adapter` decorator | Existing | None |
| `BaseAdapter[T]` protocol | Existing | None |
| `LocalToolRegistry` with auto-schema | Existing | None |
| LangGraph state machine | Existing | None |
| Sandbox service (isolated execution) | Existing | None |
| Dynamic module loading | Missing | `shared/modules/loader.py` |
| Code generation pipeline | Missing | Templates + builder tool |
| Module persistence | Missing | SQLite registry |
| Credential management | Missing | Encrypted store |

### Implementation Tiers

| Tier | Focus | New Files | Effort |
|------|-------|-----------|--------|
| 1 | Module Infrastructure (manifest, loader, dynamic categories) | 3 | 3-4 days |
| 2 | Code Generation Pipeline (templates, builder, validator) | 4 | 3-4 days |
| 3 | Lifecycle Management (persistence, credentials, health) | 3 | 2-3 days |
| 4 | Self-Evolution Loop (intent patterns, approval, install) | 1 | 3-4 days |
| 5 | Advanced (marketplace, auto-updates) | Future | 5+ days |

### End-to-End Flow
```
User: "Build me a Clash Royale stats tracker"
  -> Orchestrator detects build_module intent
  -> LLM calls build_module(name="clashroyale", category="gaming", ...)
  -> LLM generates adapter code with API-specific fetch/transform logic
  -> LLM calls validate_module("clashroyale") -> sandbox runs tests
  -> If fail: LLM debugs and retries (up to 3x)
  -> If pass: LLM asks user "ClashRoyale adapter ready. Install it?"
  -> User: "Yes"
  -> LLM calls install_module("clashroyale")
  -> Module loaded, immediately available for queries
```

---

*Document auto-generated from diff analysis. Updated: February 8, 2026.*
