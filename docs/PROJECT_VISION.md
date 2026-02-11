# NEXUS: Self-Evolving Modular Agent Framework

## Project Identity

**NEXUS** (Neural EXtensible Unified System) — A self-evolving, multi-provider agentic platform where the LLM orchestrator builds, tests, and deploys its own integration modules at runtime. The system grows organically: users describe what they want ("track my Apple Watch health metrics"), and two co-evolving agents generate, validate, and install the integration — no human coding required.

---

## Core Philosophy

### The Three Invariants

1. **Core is immutable, periphery is fluid** — The orchestrator, LLM interface, sandbox, and observability stack form a stable kernel. Everything else (adapters, tools, integrations) is a hot-swappable module that can appear or disappear without touching core code.

2. **The system builds itself** — Dual-agent co-evolution (inspired by Agent0) means a Curriculum Agent designs increasingly difficult integration challenges while an Executor Agent builds modules to solve them. The user triggers this loop with natural language; the agents handle everything from code generation to testing to deployment.

3. **Every decision is observable** — Which model handled which task, at what latency, using how much memory, for which module — all visible in real-time via Prometheus/Grafana dashboards and a React Flow pipeline editor.

---

## Architecture Overview

```
                    ┌─────────────────────────────────────────┐
                    │              SETTINGS UI                │
                    │   React Flow Pipeline + Model Control   │
                    │   Per-service model assignment           │
                    │   Orchestrator restart trigger           │
                    └────────────────┬────────────────────────┘
                                     │
┌────────────────────────────────────┼────────────────────────────────────┐
│                          CORE KERNEL (immutable)                        │
│                                                                         │
│  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  ┌──────────────┐  │
│  │ Orchestrator  │  │  LLM Client  │  │  Sandbox   │  │ Observability│  │
│  │  + LangGraph  │  │    Pool      │  │  Service   │  │    Stack     │  │
│  │  + LIDM       │  │  (multi-     │  │  (network- │  │  (Prom/Graf/ │  │
│  │  + Intent     │  │   provider)  │  │   enabled) │  │   Tempo/OTEL)│  │
│  │  + Config Mgr │  │              │  │            │  │              │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬──────┘  └──────┬───────┘  │
│         │                 │                │                 │          │
│  ┌──────┴─────────────────┴────────────────┴─────────────────┴───────┐  │
│  │                    MODULE INFRASTRUCTURE                          │  │
│  │  ModuleLoader · ModuleRegistry · CredentialStore · HealthMonitor  │  │
│  └──────────────────────────┬────────────────────────────────────────┘  │
│                             │                                           │
└─────────────────────────────┼───────────────────────────────────────────┘
                              │
        ┌─────────────────────┼──────────────────────┐
        │          MODULE LAYER (fluid)               │
        │                                             │
        │  modules/                                   │
        │  ├── finance/cibc/        (built-in)        │
        │  ├── weather/openweather/ (built-in)        │
        │  ├── gaming/clashroyale/  (LLM-generated)   │
        │  ├── health/applewatch/   (LLM-generated)   │
        │  ├── social/instagram/    (LLM-generated)   │
        │  └── ...                                    │
        │                                             │
        │  Each module:                               │
        │  ├── manifest.json                          │
        │  ├── adapter.py   (@register_adapter)       │
        │  ├── test_adapter.py                        │
        │  └── versions/v1/, v2/                      │
        └─────────────────────────────────────────────┘
```

---

## Provider Routing Strategy

The system leverages provider-specific strengths rather than treating all LLMs as interchangeable:

| Task Type | Primary Provider | Rationale |
|-----------|-----------------|-----------|
| **Code generation** (adapter building) | Claude / GPT-4 | Superior code quality, understands API patterns |
| **Google API integrations** | Google ADK / Gemini | Native understanding of Google ecosystem |
| **Unit test execution** | Local model (Qwen) | Fast iteration, no API cost for test loops |
| **Sentiment / classification** | Local model | Low latency, sufficient quality |
| **Complex reasoning** | Claude / Perplexity | Deep analysis, research tasks |
| **Simple queries** | Local model (standard tier) | Sub-second response, zero cost |

**Key principle**: The LIDM delegation manager already routes by complexity. Extend it so the `build_module` intent specifically routes code generation to online providers while test validation runs locally. The Settings UI exposes per-service model assignment, and changes trigger orchestrator reconfiguration via the existing Admin API (port 8003).

---

## Dual-Agent Co-Evolution System (Agent0-Inspired)

### Architecture

Unlike Agent0's training-time co-evolution (GRPO + ADPO on base models), NEXUS implements **inference-time co-evolution** — two agent personas operating within the existing orchestrator, sharing the LLM client pool but with distinct objectives:

```
┌─────────────────────────────────────────────────────────┐
│                  CO-EVOLUTION LOOP                        │
│                                                          │
│  ┌──────────────────┐      ┌──────────────────────┐     │
│  │ CURRICULUM AGENT  │      │   EXECUTOR AGENT     │     │
│  │                   │      │                      │     │
│  │ Generates harder  │ ───► │ Builds module to     │     │
│  │ integration tasks │      │ solve the challenge  │     │
│  │                   │ ◄─── │                      │     │
│  │ Evaluates quality │      │ Returns code + tests │     │
│  │ of built modules  │      │                      │     │
│  └──────────────────┘      └──────────────────────┘     │
│                                                          │
│  Curriculum pressures:                                   │
│  - "Build an adapter that handles paginated APIs"        │
│  - "Build one that requires OAuth2 token refresh"        │
│  - "Build one with rate limiting and retry logic"        │
│                                                          │
│  Executor improvements:                                  │
│  - Better error handling patterns learned over time      │
│  - Template evolution based on successful builds         │
│  - API pattern recognition improving with each module    │
└─────────────────────────────────────────────────────────┘
```

### How It Differs from Agent0

| Agent0 (Training-time) | NEXUS (Inference-time) |
|------------------------|----------------------|
| Trains model weights via GRPO | Improves templates + prompts via experience |
| Requires GPU cluster | Runs on existing LLM infrastructure |
| Curriculum generates math problems | Curriculum generates integration challenges |
| Executor solves problems | Executor writes adapter code |
| Pseudo-labels from majority vote | Validation from sandbox test results |
| Co-evolution improves base model | Co-evolution improves module quality + templates |

### Practical Implementation

The co-evolution runs as a **background optimization loop**, not on every user request:

1. **User-triggered builds**: User says "build me X" → Executor Agent builds it using current best templates → validates in sandbox → deploys
2. **Background evolution**: Curriculum Agent periodically generates synthetic integration challenges (harder API patterns, edge cases) → Executor Agent attempts them → successful patterns get folded back into templates
3. **Template evolution**: Templates aren't static strings — they're versioned artifacts that improve as the system builds more modules. Each successful build contributes patterns back.
4. **Failure learning**: When builds fail, the failure mode is categorized and stored. The Curriculum Agent uses failure history to generate challenges targeting weak spots.

---

## Module System Design

### Module Manifest

```json
{
  "name": "clashroyale",
  "version": "1.0.0",
  "category": "gaming",
  "platform": "clashroyale",
  "display_name": "Clash Royale Stats",
  "description": "Track player stats, battle logs, and clan info",
  "entry_point": "adapter.py",
  "class_name": "ClashRoyaleAdapter",
  "requires_api_key": true,
  "api_key_instructions": "Get your API key at https://developer.clashroyale.com",
  "python_dependencies": ["httpx"],
  "test_file": "test_adapter.py",
  "health_status": "healthy",
  "created_by": "executor_agent",
  "created_at": "2026-02-11T00:00:00Z",
  "build_provider": "claude-sonnet-4-5",
  "validation_results": {
    "syntax_check": "pass",
    "unit_tests": "pass",
    "integration_test": "pass",
    "test_coverage": 0.85
  }
}
```

### Dynamic Module Loader

```python
# Lifecycle: discover → load → register → health-check → serve
#            disable → unregister → unload → archive

class ModuleLoader:
    def load_module(self, module_path: Path) -> ModuleHandle
    def unload_module(self, module_name: str) -> bool
    def reload_module(self, module_name: str) -> ModuleHandle
    def load_all_modules(self) -> List[ModuleHandle]

    # Uses importlib.util.spec_from_file_location()
    # @register_adapter fires on import — zero pattern changes
    # Parent module pre-loaded for relative imports (critical Python requirement)
```

### Credential Store

```python
# Fernet encryption at rest, never in LLM context
class CredentialStore:
    def store(self, module_name: str, credentials: dict) -> None
    def retrieve(self, module_name: str) -> dict
    def delete(self, module_name: str) -> None

    # Master key: MODULE_ENCRYPTION_KEY env var
    # Credentials injected into AdapterConfig.credentials at load time
    # Audit log: every access traced via OTEL
```

---

## Sandbox Evolution

### Current State
- Python-only subprocess isolation
- `SAFE_IMPORTS` whitelist (math, json, re, etc.)
- No network access, no file I/O
- Memory + timeout limits

### Target State: Network-Enabled Module Sandbox

```
┌─────────────────────────────────────────────────────┐
│                 SANDBOX MODES                        │
│                                                      │
│  MODE 1: Code Execution (existing)                   │
│  - Restricted imports, no network                    │
│  - For user code snippets, math, data processing     │
│                                                      │
│  MODE 2: Module Validation (new)                     │
│  - Extended imports (httpx, aiohttp, csv, pydantic)  │
│  - Network access enabled (outbound only)            │
│  - DNS resolution allowed                            │
│  - Timeout: 60s (vs 30s for code execution)          │
│  - Memory: 512MB (vs 256MB for code execution)       │
│  - File I/O: within /tmp/module_workspace/ only      │
│                                                      │
│  MODE 3: Integration Test (new)                      │
│  - Full network access for real API calls            │
│  - Credentials injected via env vars (not in code)   │
│  - Response recording for regression tests           │
│  - Rate limit awareness                              │
└─────────────────────────────────────────────────────┘
```

**Security layers for network-enabled sandbox**:
- Outbound-only connections (no listening sockets)
- DNS allowlist configurable per module
- Request/response logging for audit
- Bandwidth and connection count limits
- Credential injection via environment, never hardcoded

---

## Observability & Control Plane

### Per-Service Model Tracking

Every LLM call gets tagged with:
```
nexus_llm_request{
  service="orchestrator",
  task_type="code_generation",
  provider="anthropic",
  model="claude-sonnet-4-5",
  module_context="clashroyale",
  tier="heavy",
  tokens_in="1234",
  tokens_out="5678",
  latency_ms="2340"
}
```

### Container Resource Monitoring

```yaml
# Prometheus scrape targets
- job_name: 'cadvisor'
  static_configs:
    - targets: ['cadvisor:8080']
  # Exposes per-container:
  # - container_memory_usage_bytes
  # - container_memory_working_set_bytes
  # - container_cpu_usage_seconds_total
  # - container_fs_usage_bytes
```

### Grafana Dashboard Panels

1. **Query Classification** — Pie chart: category distribution
2. **Model Selection Heatmap** — model x category usage patterns
3. **Inference Latency** — Time series with p50/p95/p99 by model
4. **LIDM Routing Flow** — Sankey diagram: tier transitions
5. **Container Resources** — Per-service memory/CPU gauges
6. **Module Health Matrix** — Status grid for all loaded modules
7. **Co-Evolution Progress** — Template version history, build success rates
8. **Token Economics** — Cost tracking per provider per task type

### React Flow Pipeline UI

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────┐
│ Query    │───►│ Classifier   │───►│ Tier Router   │───►│ Model    │
│ Input    │    │              │    │               │    │ Selector │
│          │    │ [category    │    │ [standard/    │    │ [provider│
│          │    │  dropdown]   │    │  heavy/ultra] │    │  config] │
└──────────┘    └──────────────┘    └───────────────┘    └────┬─────┘
                                                              │
                    ┌─────────────────────────────────────────┘
                    │
               ┌────▼─────┐    ┌──────────────┐    ┌──────────────┐
               │ Tool     │───►│ Executor     │───►│ Response     │
               │ Picker   │    │              │    │ Synthesis    │
               │          │    │ [sandbox/    │    │              │
               │ [tool    │    │  adapter/    │    │ [latency     │
               │  list]   │    │  direct]     │    │  badge]      │
               └──────────┘    └──────────────┘    └──────────────┘

Each node shows:
- Configuration controls (dropdowns, sliders)
- Live metrics badges (latency, throughput, memory)
- Color-coded health (green/yellow/red)
- Enable/disable toggles
```

---

## Self-Evolution End-to-End Flow

```
User: "Build me a Clash Royale stats tracker"
  │
  ▼
[1] Intent Detection (orchestrator/intent_patterns.py)
  │  Keywords: "build me" → build_module intent
  │  Required tools: [build_module, validate_module, install_module]
  │
  ▼
[2] LIDM Routes to Online Provider (code generation = heavy/ultra tier)
  │  Provider selected: Claude (best for code generation)
  │  Local model handles: test validation, sentiment
  │
  ▼
[3] Executor Agent calls build_module()
  │  Creates: modules/gaming/clashroyale/
  │  Generates: manifest.json, adapter.py, test_adapter.py
  │  Uses: adapter_template.py as skeleton, LLM fills API logic
  │
  ▼
[4] Executor Agent calls validate_module()
  │  Sandbox Mode 2 (module validation):
  │  ├── compile() syntax check
  │  ├── pytest test_adapter.py (mocked API)
  │  └── Verify BaseAdapter[T] compliance
  │
  ▼
[5] If FAIL: LLM self-debugs (up to 3 retries)
  │  Error details → LLM → fixed code → re-validate
  │  Uses local model for fast iteration
  │
  ▼
[6] If PASS: Human-in-the-Loop Approval
  │  LLM: "ClashRoyale adapter built and tested.
  │         Tests: 5/5 passed. Install it?"
  │  User: "Yes"
  │
  ▼
[7] install_module() → ModuleLoader.load_module()
  │  Hot-loaded into AdapterRegistry
  │  Registered in persistent ModuleRegistry (SQLite)
  │
  ▼
[8] Credential Flow (if requires_api_key)
  │  LLM: "Please provide your Clash Royale API key"
  │  User: "<key>"
  │  → CredentialStore.store() (Fernet encrypted)
  │  → Module reloaded with credentials
  │
  ▼
[9] Integration Test (Sandbox Mode 3)
  │  Real API call with user's credentials
  │  Validates actual data flow
  │
  ▼
[10] Module Live
   │  Added to user memory context
   │  Available for queries: "Show my Clash Royale stats"
   │  Health monitored via circuit breaker
   │  Metrics flowing to Prometheus
```

---

## Compatibility with Current Architecture

| Component | Status | Integration Point |
|-----------|--------|-------------------|
| `@register_adapter` decorator | **Exact reuse** | Fires on dynamic import, zero changes |
| `BaseAdapter[T]` protocol | **Exact reuse** | Generated code follows same pattern |
| `LocalToolRegistry` | **Extend** | Add build/validate/install tools |
| `LangGraph state machine` | **Extend** | New `build_module` path in graph |
| `LLMClientPool` | **Exact reuse** | Routes build tasks via LIDM |
| `ConfigManager` | **Exact reuse** | Hot-reload model assignments |
| `Sandbox service` | **Extend** | Add Mode 2 (validation) + Mode 3 (integration) |
| `AdapterRegistry` | **Exact reuse** | Dynamic modules register alongside built-ins |
| `OTEL / Prometheus` | **Extend** | Add module-specific + container metrics |
| `Admin API (:8003)` | **Extend** | Add module management endpoints |
| OpenAI-compatible API spec | **No change** | All providers use same interface |
| Docker Compose | **Extend** | Mount `modules/` volume, add cAdvisor |

**Breaking changes: ZERO.** The entire module system is additive.

---

## Implementation Tracks (Parallel)

### Track A: Module Infrastructure (Tiers 1-4)

| Phase | Scope | Files |
|-------|-------|-------|
| A1 | Manifest + Loader + Dynamic categories | `shared/modules/{__init__, manifest, loader}.py` |
| A2 | Templates + Builder tool + Validator tool | `shared/modules/templates/`, `tools/builtin/module_{builder,validator}.py` |
| A3 | Persistent registry + Credential store + Health | `shared/modules/{registry, credentials}.py`, `tools/builtin/module_manager.py` |
| A4 | Self-evolution loop + Intent + Approval + Install | `tools/builtin/module_installer.py`, intent patterns, graph extension |

### Track B: Observability & Control UI

| Phase | Scope | Files |
|-------|-------|-------|
| B1 | Metrics instrumentation + cAdvisor | `shared/observability/metrics.py`, docker-compose cAdvisor service |
| B2 | Prometheus config + Grafana dashboards | `config/prometheus/`, `config/grafana/dashboards/` |
| B3 | React Flow pipeline UI | `ui_service/src/pages/settings/routing.tsx` |
| B4 | Settings UI model control + restart trigger | Admin API extensions, UI integration |

### Track C: Co-Evolution System

| Phase | Scope | Files |
|-------|-------|-------|
| C1 | Curriculum Agent persona + challenge generation | `orchestrator/coevolution/curriculum_agent.py` |
| C2 | Executor Agent persona + template evolution | `orchestrator/coevolution/executor_agent.py` |
| C3 | Evolution loop scheduler + progress tracking | `orchestrator/coevolution/evolution_loop.py` |
| C4 | Template versioning + failure learning | `shared/modules/templates/evolution/` |

---

## Security Model

| Layer | Mechanism | Status |
|-------|-----------|--------|
| Code execution isolation | Sandbox subprocess (existing) + network-enabled mode (new) | Extend |
| Import restriction | `SAFE_IMPORTS` whitelist per sandbox mode | Extend |
| Resource limits | Timeout + memory per mode (30s/256MB, 60s/512MB) | Extend |
| Network control | Outbound-only, DNS allowlist, bandwidth limits | New |
| Human approval gate | Required before module deployment | New |
| Credential encryption | Fernet at rest, env injection, never in LLM context | New |
| Circuit breaker | Auto-disable after repeated failures (existing) | Reuse |
| Rate limiting | Per-adapter `rate_limit_per_minute` (existing) | Reuse |
| Audit trail | OTEL tracing for all module lifecycle events | Extend |
| Container isolation | Docker network, no auth on internal gRPC | Existing |
| Generated code review | Static analysis before loading (compile + AST check) | New |

---

## What Makes This Different

1. **Not just a plugin system** — Most frameworks let you *manually add* plugins. NEXUS lets the LLM *build* plugins. The system literally extends its own capabilities through conversation.

2. **Not just code generation** — The code is tested, validated, approved by the user, deployed, monitored, and auto-disabled if it breaks. Full lifecycle, not just generation.

3. **Provider-aware routing** — Google ADK for Google APIs, Claude for code generation, local models for fast iteration. Each task uses the best available tool, not a one-size-fits-all approach.

4. **Co-evolution, not static templates** — Templates improve over time as the system builds more modules. The Curriculum Agent pushes the Executor to handle harder patterns. The system gets better at building modules the more it builds.

5. **Observable and controllable** — Every LLM decision, every model choice, every container's memory usage — visible in real-time. The React Flow UI lets operators understand and tune the pipeline visually.

---

## Open Questions for Future Phases

1. **Module marketplace**: Should modules be shareable between NEXUS instances via a GitHub-backed registry?
2. **Auto-healing**: When a module's API changes and tests start failing, should the Executor Agent automatically attempt to regenerate it?
3. **Multi-language modules**: Should modules be Python-only, or support TypeScript/Go adapters running as separate containers?
4. **Federated learning**: Could multiple NEXUS instances share template improvements without sharing user data?
