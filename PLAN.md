Build Configurable Multi-Provider Agent UI
Create a modular settings UI for your gRPC LLM framework that enables runtime configuration of LLM providers, tools, and inference endpoints—implementing the "control plane" pattern that separates orchestration configuration from execution.

---

## Document Conventions
- Sections above the Appendix are the active roadmap.
- The Appendix is preserved verbatim-ish for full context, but may contain duplicates/outdated sequences.
- When in doubt, treat the checklists in “IMPLEMENTATION PROGRESS” and the explicit TODO blocks as the current source of truth.

## Table of Contents
- [Recent Changes & Notes](#recent-changes)
- [Implementation Progress](#implementation-progress)
- [Architecture Evaluation & Critical Actions](#architecture-evaluation) ← **NEW**
- [Cleanup Plan](#cleanup-plan)
- [Running-Container Testing Cookbook](#docker-testing)
- [Clawdbot Workstream](#clawdbot-workstream)
- [Optional Research Track](#research-track)
- [Architecture (Dashboard)](#architecture-dashboard)
- [Appendix (Archived Draft Notes)](#appendix-archived)

<a id="recent-changes"></a>

## ✅ RECENT CHANGES & NOTES (Updated: January 31, 2026)

### What Changed (last working session)
- Provider runtime: switched default LLM provider usage to Perplexity Sonar (OpenAI-compatible API) to improve tool selection reliability vs. tiny local models.
- Orchestrator tool-calling: hardened parsing so responses containing mixed content (e.g., JSON wrapped in markdown fences or JSON + extra prose) still execute.
- Tool results + multi-step flow: revised prompt/loop behavior so the model can continue calling tools after tool results when needed.
- Tool robustness:
  - `get_commute_time()` now matches destinations via saved destination address as well as key/name.
  - Added alias handling so “work” can resolve to the same destination as “office”.
- Ops/devex: expanded Makefile commands for provider switching, service lifecycle, health checks, and smoke tests.
- UI settings: fixed container env path assumptions that caused `ENOENT: no such file or directory, open '/app/.env'`.

### Pain Points (Root Causes)
- LLM output discipline: some providers/models return tool-call JSON wrapped in ```json fences or mixed with narrative text.
- Multi-step intent ambiguity: “What time should I leave?” requires calendar + commute; the model sometimes answers early without calling the second tool.
- Parameter grounding: the model sometimes uses meeting titles as `destination` instead of resolving to `office/work`.
- Docker caching: code changes (especially tools) can be masked by cached layers/containers; forced rebuild/recreate is sometimes required.

### Immediate Outcome
- Multi-tool queries like “meeting time + commute to office” now reliably execute both tools and synthesize a clean answer.
- Remaining gap: ambiguous “leave time” queries need a clearer destination resolution strategy (infer from meeting location, map common terms, or ask a single follow-up).

<a id="implementation-progress"></a>

## 🎯 IMPLEMENTATION PROGRESS (Updated: January 31, 2026)

### ✅ COMPLETED

#### Phase 1: Provider Abstraction Layer
- [x] `shared/providers/base_provider.py` - Abstract BaseProvider class with generate/stream interfaces
- [x] `shared/providers/local_provider.py` - Wraps existing LLMClient for llama.cpp
- [x] `shared/providers/anthropic_provider.py` - Claude API integration
- [x] `shared/providers/openai_provider.py` - OpenAI GPT-4/o3 integration
- [x] `shared/providers/perplexity_provider.py` - Sonar search/reasoning
- [x] `shared/providers/registry.py` - Provider registration and routing

#### Phase 2: Settings UI
- [x] `ui_service/src/components/settings/SettingsPanel.tsx` - Provider selection UI
- [x] `ui_service/src/app/api/settings/route.ts` - Settings API endpoint
- [x] Provider switching with status indicators
- [x] API key configuration (server-side storage in .env)

#### Phase 3: Conversation History & Context
- [x] `ui_service/src/components/history/ConversationHistory.tsx` - Sidebar with conversation list
- [x] `ui_service/src/app/api/conversations/route.ts` - CRUD for conversations
- [x] Auto-save with debounce (2s delay)
- [x] Auto-summarization at 20 message threshold
- [x] `ui_service/src/app/api/summarize/route.ts` - LLM-powered summarization

#### Phase 4: User Data Container Dashboard ✨ NEW
- [x] **Canonical Data Schemas** (`shared/schemas/canonical.py`)
  - FinancialTransaction, FinancialAccount, TransactionCategory
  - CalendarEvent, EventStatus, RecurrenceRule
  - HealthMetric, MetricType, HealthSummary
  - NavigationRoute, TrafficLevel, GeoPoint
  - Contact, UnifiedContext
  
- [x] **Adapter Pattern** (`shared/adapters/`)
  - `base.py` - Protocol-based adapter interface
  - `registry.py` - @register_adapter decorator, singleton registry
  - Mock adapters for all 4 categories (finance, calendar, health, navigation)
  
- [x] **Dashboard Aggregator** (`dashboard_service/`)
  - `aggregator.py` - Parallel fetching, caching, context building
  - `relevance.py` - HIGH/MEDIUM/LOW classification engine
  
- [x] **Dashboard UI** (`ui_service/src/components/dashboard/`)
  - `Dashboard.tsx` - Main container with grid/row/column/focus views
  - `CalendarWidget.tsx` - Events with urgency indicators
  - `FinanceWidget.tsx` - Transactions, cashflow, spending
  - `HealthWidget.tsx` - Steps, HRV, sleep, readiness
  - `NavigationWidget.tsx` - Routes, traffic, ETA
  - `HighPriorityAlerts.tsx` - Relevance-based alerts
  - `AdaptersPanel.tsx` - Connect/disconnect data sources
  
- [x] **Dashboard API** (`ui_service/src/app/api/dashboard/`)
  - `route.ts` - GET unified context, POST config
  - `adapters/route.ts` - List, connect, disconnect adapters
  
- [x] **LLM Tool Integration** (`tools/builtin/user_context.py`)
  - `get_user_context` - Retrieve user's personal context for LLM
  - `get_daily_briefing` - Quick daily summary
  - Natural language summaries for calendar, finance, health, navigation

- [x] **Flexible UI**
  - Fullscreen dashboard mode
  - Grid/Row/Column layout options
  - Panel toggle buttons (show/hide categories)
  - Side panel and fullscreen modes in ChatContainer

### 🔄 IN PROGRESS

#### Phase 5: Real Adapter Integrations
- [ ] Google Calendar OAuth adapter
- [ ] Plaid/Wealthsimple finance adapter
- [ ] Apple Health / Oura / Whoop adapter
- [ ] Google Maps / Waze adapter

#### Phase 6: Multi-User & Persistence
- [ ] PostgreSQL migration with RLS
- [ ] User authentication (NextAuth.js)
- [ ] Per-user settings storage

### 📋 PLANNED

#### Phase 7: MCP Integration
- [ ] @mcp_tool decorator implementation
- [ ] Perplexity MCP server bridge
- [ ] Auto-discovery of MCP tools

#### Phase 8: Clawdbot Entry Point
- [ ] IInputAdapter interface
- [ ] Telegram/Discord bot adapter
- [ ] Message bus (Redis Streams)
- [ ] See detailed workstream: “NEW WORKSTREAM: CLAWDBOT AS A DOCKERIZED MICROSERVICE”

---

<a id="architecture-evaluation"></a>

## 🏗️ ARCHITECTURE EVALUATION & CRITICAL ACTIONS

*Living roadmap for infrastructure and reliability improvements. Updated: February 1, 2026*

### Current State Summary

| Component | Status | Scalability | Extensibility |
|-----------|--------|-------------|---------------|
| Provider Layer | ✅ Good | Medium | High |
| Tool Registry | ✅ Good | Low | High |
| Checkpointing | ⚠️ SQLite only | Low | Medium |
| Observability | ✅ Integrated | Medium | High |
| Database | ⚠️ SQLite only | Low | Low |
| RL/Curriculum | ✅ Foundation | Medium | High |

### Microservice Architecture Guide

| Service | Role | Key Functionality |
|---------|------|------------------|
| **Orchestrator** | Central Nervous System | Request lifecycle, Provider routing, Tool execution, RL state tracking |
| **LLM Service** | Inference Engine | Wraps local models (llama.cpp) or acts as proxy for embeddings/generation |
| **Chroma Service** | Long-term Memory | Vector database for RAG (Retrieval Augmented Generation) |
| **Registry Service** | Configuration | Tracks available tools, service health, prompt templates |
| **Sandbox Service** | Safety Containment | Executes unstable code (Python) in isolated environment |
| **Dashboard Service** | User Data Aggregator | Fetches personal data (Calendar, Finance, Health) via adapters |
| **Clawdbot** (Planned) | Entry Gateway | Telegram/Discord bot interface for "frontend-less" access |

### Critical Actions (Priority 1)

- [x] **Observability Stack** - Prometheus + Grafana + structured logging *(Feb 1, 2026)*
- [ ] **PostgreSQL Migration** - Replace SQLite for shared state
- [ ] **Rate Limiting** - Token bucket per provider

### High Priority (Agent0/ToolOrchestra)

- [x] **Metrics Collection** - Endpoint stats, tool frequency, cost tracking *(Feb 1, 2026)*
- [x] **Dynamic Provider Router** - Fallback chains (local → perplexity → claude) *(Feb 1, 2026)*
- [ ] **Self-Consistency Integration** - Enable and use uncertainty signal

### Medium Priority

- [x] **Dashboard Service Containerization** - Real adapters in Docker *(Feb 1, 2026)*
- [ ] **Message Queue (Redis)** - Async job processing
- [ ] **Health Checks Fix** - Reliable health endpoints

### Implementation Roadmap (Living Checklist)

```
┌──────┬──────────────────────┬───────────────────────────────────────────────┬────────┬─────────┐
│ Week │ Focus                │ Deliverables                                  │ Owner  │ Status  │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 1    │ Observability        │ Prometheus + Grafana + structured logging     │ Claude │ ✅      │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 2    │ Database             │ PostgreSQL migration, connection pooling      │ Claude │ ⬜      │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 3    │ Provider Router      │ Dynamic selection, fallback chains            │ Claude │ ✅      │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 4    │ Metrics Collection   │ Endpoint stats, tool frequency, cost tracking │ Claude │ ✅      │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 5    │ RL Foundation        │ Reward function, offline training pipeline    │ Claude │ ✅      │
├──────┼──────────────────────┼───────────────────────────────────────────────┼────────┼─────────┤
│ 6    │ Clawdbot Integration │ Bidirectional gRPC, Telegram gateway          │ Claude │ 🔄 In Progress|
└──────┴──────────────────────┴───────────────────────────────────────────────┴────────┴─────────┘
```

### Sprint Details (Key Patterns)

<details>
<summary><b>Week 3: Provider Router Pattern</b></summary>

```python
# orchestrator/provider_router.py
class ProviderRouter:
    """Dynamic provider selection with fallback chains."""

    FALLBACK_CHAIN = ["local", "perplexity", "claude"]

    def select_provider(self, query: str, context: Dict) -> str:
        complexity = self._estimate_complexity(query)
        if complexity < 0.3:
            return "local"  # Fast, cheap
        elif complexity < 0.7:
            return "perplexity"  # Search-augmented
        else:
            return "claude"  # Complex reasoning
```
</details>

<details>
<summary><b>Week 4: Metrics Collection Pattern</b></summary>

```python
# orchestrator/rl/metrics.py
@dataclass
class EndpointMetrics:
    success_rate: Dict[str, float]  # per provider
    avg_latency_ms: Dict[str, float]
    tool_frequency: Dict[str, int]
    cost_usd: Dict[str, float]

    def to_prometheus(self) -> List[Metric]:
        """Export for Prometheus scraping."""
```
</details>

<details>
<summary><b>Week 5: Agent0 Reward Function (Simplified)</b></summary>

```python
# orchestrator/rl/reward.py
def compute_reward(task, responses, tools_used, cost) -> float:
    """
    R = α·uncertainty + β·tool_complexity + γ·cost_efficiency

    - uncertainty: variance in executor responses (self-consistency)
    - tool_complexity: diversity × avg tool difficulty
    - cost_efficiency: 1/(1+cost)
    """
    R_uncertainty = self._compute_disagreement(responses)
    R_tool = self._compute_tool_score(tools_used)
    R_cost = 1.0 / (1.0 + cost)

    return 0.5*R_uncertainty + 0.3*R_tool + 0.2*R_cost
```
</details>

---

<a id="cleanup-plan"></a>

## 🧹 CLEANUP PLAN (Complexity & Reliability)

→ *See [Architecture Evaluation](#architecture-evaluation) for observability and database migration actions*

### A) Tool-Calling Reliability (Orchestrator)
- [ ] Consolidate “tool-call JSON parsing” into a single utility (strip markdown fences, extract the first valid JSON object, ignore trailing prose).
- [ ] Add a multi-step guardrail for “leave time” queries:
  - require destination resolution (`office/work/home/...`)
  - if not resolvable from context, ask one clarifying question
- [ ] Reduce/debug logging added during investigations; keep only tool-call detection, arguments, tool result status/latency, and final synthesis.

### B) Tool Layer Cleanup
- [ ] Normalize destination aliases across tools (`office`, `work`, `the office`, etc.) in one place.
- [ ] Add unit tests for destination matching (key/name/address/alias) and “unknown destination” behavior.

### C) Docker/Build Hygiene
- [ ] Add explicit “cache bust” make targets for fast iteration on `orchestrator` and `tools`.
- [ ] Document when to use `--no-cache` vs `--force-recreate` to avoid “container has old code” confusion.
- [ ] Reduce rebuild cost by shrinking build contexts where possible (especially large model artifacts).

---

<a id="docker-testing"></a>

## 🧪 RUNNING-CONTAINER TESTING COOKBOOK (Docker + gRPC)

### Inspect the stack
- List running containers: `docker compose ps`
- Tail logs (example): `docker logs -f orchestrator --tail 200`

### Verify gRPC surface (reflection)
- List services: `grpcurl -plaintext localhost:50054 list`
- Describe service: `grpcurl -plaintext localhost:50054 describe agent.AgentService`

### Issue a basic query
Orchestrator method: `agent.AgentService/QueryAgent` with field `user_query`.

- Example:
  - `grpcurl -plaintext -d '{"user_query":"What time is my 1:1 with Manager meeting?"}' localhost:50054 agent.AgentService/QueryAgent`

### Debug tool execution
- Grep for tool calls in logs:
  - `docker logs orchestrator --tail 200 | grep -E "Tool call|Tool get_|Final answer"`
- Sanity-check tool data inside the container (useful when Docker caching bites):
  - `docker exec orchestrator python -c "from tools.builtin.user_context import _get_mock_context; print(sorted(_get_mock_context()['navigation']['saved_destinations'].keys()))"`

### Force a rebuild when changes don’t show up
Try these in increasing strength:

- Restart: `docker compose restart orchestrator`
- Rebuild + up: `docker compose build orchestrator && docker compose up -d orchestrator`
- Force recreate: `docker compose up -d --force-recreate orchestrator`
- Hard reset (when cached layers keep stale code):
  - `docker rmi grpc_llm-orchestrator:latest -f && docker compose build --no-cache orchestrator && docker compose up -d orchestrator`

---

<a id="clawdbot-workstream"></a>

## 🧩 NEW WORKSTREAM: CLAWDBOT AS A DOCKERIZED MICROSERVICE (Entry Gateway)

→ *See [Architecture Evaluation Week 6](#architecture-evaluation) for integration timeline*

### Goal
Add Clawdbot as an external-facing gateway (Telegram + local UI) that can:
- fetch dashboard context (HTTP)
- delegate reasoning to orchestrator (gRPC)
- optionally expose a callback gRPC service for notifications

### TODOs (Clawdbot integration)
- [ ] Extend `docker-compose.yaml` with a new `clawdbot` service.
- [ ] Add `shared/proto/clawdbot.proto` (example: SendMessage, GetContextSnapshot).
- [ ] Generate protobuf stubs into `shared/generated/` and add a minimal client wrapper under `shared/clients/`.
- [ ] Decide directionality:
  - Clawdbot -> Orchestrator for “pull” reasoning (required)
  - Orchestrator -> Clawdbot callback for “push” notifications (optional)
- [ ] Add an integration test:
  - spin services
  - call Clawdbot gRPC
  - verify it can call orchestrator and return a message

---

<a id="research-track"></a>

## 🔭 OPTIONAL RESEARCH TRACK: Agent0 / ToolOrchestra-style routing

→ *See [Architecture Evaluation Week 4-5](#architecture-evaluation) for metrics and RL foundation*

Keep this as a separate track from stability + settings control plane.

### TODOs (future)
- [ ] Define a lightweight routing policy interface (no RL yet): heuristic-based “escalate provider” rules using tool frequency + uncertainty.
- [ ] Add structured metrics: tool call counts, failures, provider latency, token usage.
- [ ] Add self-consistency sampling toggles per request or per conversation, store outcomes for routing analysis.

<a id="architecture-dashboard"></a>

## Architecture: User Data Container Dashboard

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         USER DATA CONTAINER DASHBOARD                        │
│                      (Data-Oriented Polymorphism Design)                     │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                        CANONICAL SCHEMAS                             │   │
│  │  shared/schemas/canonical.py                                         │   │
│  │  • Platform-agnostic data structures                                 │   │
│  │  • FinancialTransaction, CalendarEvent, HealthMetric, NavigationRoute│   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      CATEGORY-FIRST ADAPTERS                         │   │
│  │  shared/adapters/                                                    │   │
│  │  ├── finance/   (wealthsimple, cibc, affirm, plaid)                  │   │
│  │  ├── calendar/  (google, apple, outlook)                             │   │
│  │  ├── health/    (apple_health, oura, whoop, fitbit, garmin)          │   │
│  │  └── navigation/(google_maps, apple_maps, waze)                      │   │
│  │                                                                      │   │
│  │  Protocol: Adapter.fetch() → CanonicalType                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                     DASHBOARD AGGREGATOR                             │   │
│  │  dashboard_service/aggregator.py                                     │   │
│  │  • Parallel fetching from all adapters                               │   │
│  │  • In-memory cache with TTL                                          │   │
│  │  • Unified context building                                          │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                                    ▼                                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │                      RELEVANCE ENGINE                                │   │
│  │  dashboard_service/relevance.py                                      │   │
│  │  • HIGH: Calendar <2h, budget exceeded, low HRV, heavy traffic       │   │
│  │  • MEDIUM: Events 2-24h, pending transactions                        │   │
│  │  • LOW: Events >24h, historical data                                 │   │
│  │                                                                      │   │
│  │  Storage Tiering: HIGH→Redis, MEDIUM→PostgreSQL, LOW→S3              │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                    │                                        │
│                    ┌───────────────┴───────────────┐                       │
│                    ▼                               ▼                        │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────────┐ │
│  │      DASHBOARD UI           │  │        LLM TOOL                      │ │
│  │  components/dashboard/      │  │  tools/builtin/user_context.py      │ │
│  │  • Grid/Row/Column layouts  │  │  • get_user_context                  │ │
│  │  • Fullscreen mode          │  │  • get_daily_briefing                │ │
│  │  • Panel toggle controls    │  │  • Natural language summaries        │ │
│  │  • High priority alerts     │  │  • Personalized LLM responses        │ │
│  └─────────────────────────────┘  └─────────────────────────────────────┘ │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

<a id="appendix-archived"></a>

## Appendix: Archived Draft Notes (Reference)
These sections are kept to preserve the full narrative/design space explored so far. They may include duplicated plans or steps that are already completed.

<details>
<summary>Click to expand archived drafts</summary>

### Legacy Draft: “Steps” (ARCHIVED)

Create Settings gRPC Service — Add shared/proto/settings.proto defining SettingsService with RPCs: GetConfig, UpdateConfig, ListProviders, ListTools, SetToolState. This becomes the central configuration contract.

Implement Settings Backend — Create settings_service/ or extend orchestrator_service.py with a SettingsServicer that persists config to SQLite (reusing checkpointing pattern), supports hot-reload of tools, and validates provider credentials.

Build Settings UI Pages — Add to app three new routes: /settings/providers (LLM selector), /settings/tools (tool toggle grid), /settings/inference (temperature, max tokens, self-consistency).

Create Provider Abstraction Layer — Extend llm_client.py into a MultiProviderClient supporting: local (llama.cpp via existing LLM service), Claude API, OpenAI API, Gemini API, Perplexity API—selected via config.

Add Tool Configuration Store — Extend registry.py with enable_tool(name), disable_tool(name), get_tool_states() methods, persisted to SQLite alongside conversation checkpoints.

Wire UI to gRPC Settings API — Add ui_service/src/lib/settings-client.ts and ui_service/src/app/api/settings/route.ts to bridge Next.js UI to the new gRPC SettingsService.

Further Considerations
Provider Credentials Security? Store API keys server-side only (env vars) vs. allow UI key entry with encryption? Recommend: UI shows "configured" status but keys stay in .env for security.

Per-Conversation vs. Global Settings? Should tool/provider config be per-thread (stored with checkpoint) or global (system-wide)? Could support both: global defaults + per-conversation overrides.

Hot-Reload vs. Restart? Tool enable/disable could work hot (registry already supports dynamic registration). Provider switching may require connection pool management—implement graceful handoff?

Why This Is Groundbreaking
Based on the Perplexity research and your architecture, here's why this approach represents a paradigm shift:

1. "Swap, Don't Stack" Becomes Real
Current AI platforms force vendor lock-in. Your architecture enables:

Scenario	How Your UI Handles It
Claude rate-limited	Toggle to Gemini mid-conversation
Local inference for privacy	Switch to llama.cpp for sensitive queries
Cost optimization	Route simple queries to Sonar, complex to Claude
Compliance requirements	Disable external APIs, use only local models
No other open-source framework provides this level of runtime provider switching with conversation continuity.

2. Tool Registry as Capability Marketplace
Your LocalToolRegistry + UI becomes a plugin system:
```
┌─────────────────────────────────────────────────────────────┐
│                    Tool Configuration UI                    │
├──────────────┬──────────┬───────────────┬──────────────────┤
│ 🔍 web_search │ ✅ ON    │ Serper API    │ 2,483/2,500 left │
│ 🧮 math_solver│ ✅ ON    │ Local         │ No limits        │
│ 🐍 execute_code│ ✅ ON   │ Sandbox       │ 30s timeout      │
│ 🌐 perplexity │ ⬜ OFF   │ Not configured│ Add API key →    │
│ 🤖 claude_direct│ ⬜ OFF │ Anthropic API │ Add API key →    │
└──────────────┴──────────┴───────────────┴──────────────────┘
```
This makes your agent self-documenting—users see exactly what capabilities are available and their status.

3. Hybrid Inference Control Plane
The research shows leading platforms (Dify, LangGraph Studio) lack unified local+cloud orchestration. Your architecture uniquely supports:

Single conversation can use multiple providers based on task requirements.
```
User Query → Orchestrator → Provider Router
                              ├── Local: llm_service (50051) - llama.cpp
                              ├── Cloud: Claude API (direct)
                              ├── Cloud: OpenAI API (direct)
                              ├── Cloud: Gemini API (direct)
                              └── Search: Perplexity Sonar API
```
4. MCP-Ready Architecture
Your @mcp_tool decorator in decorators.py is a placeholder for Phase 1C. When complete:
```
@mcp_tool(
    server_command='npx',
    server_args=["-y", "perplexity-mcp"],
    env={"PERPLEXITY_API_KEY": "${PERPLEXITY_API_KEY}"}
)
class PerplexityTools:
    pass  # Auto-discovered from MCP server
```
Your UI becomes an MCP tool discovery interface—automatically populating available tools from any MCP-compliant server.

5. Enterprise-Grade with Open-Source Flexibility
Feature	Enterprise Platforms	Your Framework
Multi-provider	❌ Vendor lock-in	✅ Any provider
Local inference	❌ Cloud-only	✅ llama.cpp native
Tool hot-swap	❌ Restart required	✅ Runtime toggle
gRPC contracts	❌ REST/proprietary	✅ Type-safe protos
Crash recovery	⚠️ Limited	✅ SQLite WAL
Self-consistency	❌ Not available	✅ Agent0 Phase 2


--- 

Scalable Multi-User AI Agent Configuration Platform
Design a production-grade, multi-tenant architecture for your gRPC LLM framework with a parameterized configuration UI, supporting 10k+ concurrent users with provider/tool configurability.
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PRESENTATION LAYER                             │
├─────────────────────────────────────────────────────────────────────────────┤
│  Next.js 14 (App Router)                                                    │
│  ├── /app/page.tsx (Chat UI)                                                │
│  ├── /app/settings/providers/page.tsx (LLM Provider Config)                 │
│  ├── /app/settings/tools/page.tsx (Tool Registry UI)                        │
│  ├── /app/settings/inference/page.tsx (Model Parameters)                    │
│  └── /app/auth/ (NextAuth.js - OAuth/JWT)                                   │
│                                                                             │
│  WebSocket/SSE ←→ API Routes ←→ gRPC Gateway                                │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                              GATEWAY LAYER                                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  Kong/Envoy API Gateway                                                     │
│  ├── Rate Limiting (per user/org)                                           │
│  ├── JWT Validation                                                         │
│  ├── gRPC Transcoding (REST → gRPC)                                         │
│  └── Load Balancing (round-robin to orchestrators)                          │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           ORCHESTRATION LAYER                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Orchestrator Service (50054) - Horizontally Scaled                         │
│  ├── AuthInterceptor (JWT validation, tenant extraction)                    │
│  ├── ConfigService (per-user/org settings)                                  │
│  ├── ProviderRouter (multi-LLM selection)                                   │
│  ├── ToolRegistry (dynamic enable/disable)                                  │
│  └── LangGraph StateMachine (llm → tools → validate)                        │
│                                                                             │
│  New gRPC Services:                                                         │
│  ├── SettingsService (GetConfig, UpdateConfig, ListProviders, ListTools)    │
│  └── UsageService (GetUsage, GetQuota)                                      │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
┌──────────────────────┐ ┌──────────────────┐ ┌──────────────────────┐
│   INFERENCE LAYER    │ │   TOOL LAYER     │ │   EXTERNAL APIS      │
├──────────────────────┤ ├──────────────────┤ ├──────────────────────┤
│ Local LLM (50051)    │ │ Sandbox (50057)  │ │ Claude API           │
│ ├── llama.cpp        │ │ Workers (50056)  │ │ OpenAI API           │
│ └── GPU Inference    │ │ Chroma (50052)   │ │ Gemini API           │
│                      │ │                  │ │ Perplexity API       │
│ Connection Pool      │ │ Circuit Breakers │ │ Serper API           │
└──────────────────────┘ └──────────────────┘ └──────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                            PERSISTENCE LAYER                                │
├─────────────────────────────────────────────────────────────────────────────┤
│  PostgreSQL (Primary - Multi-tenant)                                        │
│  ├── checkpoints (tenant_id, user_id, thread_id, state JSONB)               │
│  ├── user_settings (tenant_id, user_id, config JSONB)                       │
│  ├── usage_logs (tenant_id, user_id, provider, tokens, cost, timestamp)     │
│  └── Row-Level Security (RLS) policies per tenant                           │
│                                                                             │
│  Redis (Session + Cache)                                                    │
│  ├── Session tokens (TTL 24h)                                               │
│  ├── Semantic cache (GPTCache pattern)                                      │
│  ├── Rate limit counters (sliding window)                                   │
│  └── Quota tracking (daily/monthly budgets)                                 │
│                                                                             │
│  ChromaDB (Vector - Tenant-Sharded)                                         │
│  └── Collections per tenant for RAG isolation                               │
└─────────────────────────────────────────────────────────────────────────────┘
```
Architecture Overview
Implementation Steps
Phase 1: Multi-Tenant Foundation (Week 1-2)
Migrate SQLite → PostgreSQL with RLS — Create shared/db/schema.sql with tenant-isolated tables for checkpoints, settings, usage. Add tenant_id + user_id columns, RLS policies, and partitioning.

Add gRPC Auth Interceptor — Create shared/interceptors/auth_interceptor.py extracting JWT from metadata, validating via Redis-cached keys, injecting user_id/tenant_id into context.

Extend AgentState for Multi-Tenancy — Modify state.py to require user_id and tenant_id, update create_initial_state() and all callers in orchestrator.

Add Redis for Sessions/Cache — Create shared/cache/redis_client.py with connection pooling, rate limiting helpers, and semantic cache integration.

Phase 2: Settings Service (Week 2-3)
Define Settings Proto — Create shared/proto/settings.proto:
```
service SettingsService {
  rpc GetUserConfig(GetConfigRequest) returns (UserConfig);
  rpc UpdateUserConfig(UpdateConfigRequest) returns (UserConfig);
  rpc ListProviders(Empty) returns (ProviderList);
  rpc ListTools(Empty) returns (ToolList);
  rpc SetToolState(SetToolStateRequest) returns (ToolState);
}

message UserConfig {
  string default_provider = 1;  // "local", "claude", "openai", "gemini"
  float temperature = 2;
  int32 max_tokens = 3;
  bool enable_self_consistency = 4;
  repeated string enabled_tools = 5;
  map<string, string> provider_configs = 6;
}
```
Implement SettingsServicer — Add to orchestrator_service.py or new settings_service/ handling config CRUD with PostgreSQL persistence.

Build Provider Router — Create shared/clients/provider_router.py abstracting local/Claude/OpenAI/Gemini/Perplexity behind unified interface, selected per-request based on user config.

Phase 3: Configuration UI (Week 3-4)
Add NextAuth.js — Integrate in ui_service/src/app/api/auth/ for OAuth (Google, GitHub) + JWT session management.

Create Settings Pages — Build three new routes:

ui_service/src/app/settings/providers/page.tsx — Provider cards with status, API key configuration
ui_service/src/app/settings/tools/page.tsx — Tool toggle grid with circuit breaker status
ui_service/src/app/settings/inference/page.tsx — Sliders for temperature, max_tokens, self-consistency
Wire gRPC Settings Client — Create ui_service/src/lib/settings-client.ts + ui_service/src/app/api/settings/route.ts bridging UI to SettingsService.

Phase 4: Observability & Scaling (Week 4-5)
Add OpenTelemetry — Instrument orchestrator_service.py with traces (tool calls, LLM latency), metrics (token usage, cost per user), export to Jaeger.

Implement Usage Tracking — Create usage_service/ or extend orchestrator with token counting, cost calculation, daily/monthly aggregation per user/org.

Kubernetes Manifests — Create k8s/ directory with HPA for orchestrator, GPU scheduling for llm_service, Envoy sidecars for gRPC load balancing.

Key Technical Decisions
Decision	Recommendation	Rationale
Database	PostgreSQL + RLS	ACID, concurrent writes, row-level security for tenant isolation
Session Cache	Redis	Sub-ms latency, built-in rate limiting, TTL support
Message Queue	Redis Streams (MVP) → Kafka (scale)	Simplicity now, Kafka when >100k msg/s needed
Auth	NextAuth.js + JWT	Works with Next.js, supports OAuth providers
Provider Abstraction	Unified client interface	Hot-swap providers without code changes
Tool Config	Per-user settings in PostgreSQL	Persist preferences, enable per-user customization
Database Schema (PostgreSQL)
```
-- Enable RLS
ALTER DATABASE agent_db SET row_security = on;

-- Tenants/Organizations
CREATE TABLE tenants (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Users
CREATE TABLE users (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID REFERENCES tenants(id),
    email TEXT UNIQUE NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Checkpoints (LangGraph state)
CREATE TABLE checkpoints (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL REFERENCES tenants(id),
    user_id UUID NOT NULL REFERENCES users(id),
    thread_id TEXT NOT NULL,
    checkpoint_id TEXT NOT NULL,
    parent_id TEXT,
    state JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(thread_id, checkpoint_id)
);
CREATE INDEX idx_checkpoints_user_thread ON checkpoints(user_id, thread_id);

-- RLS Policy
ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;
CREATE POLICY tenant_isolation ON checkpoints
    USING (tenant_id = current_setting('app.tenant_id')::uuid);

-- Usage Tracking (TimescaleDB hypertable recommended)
CREATE TABLE usage_logs (
    id UUID DEFAULT gen_random_uuid(),
    tenant_id UUID NOT NULL,
    user_id UUID NOT NULL,
    provider TEXT NOT NULL,  -- 'local', 'claude', 'openai', etc.
    model TEXT NOT NULL,
    prompt_tokens INT NOT NULL,
    completion_tokens INT NOT NULL,
    cost_usd DECIMAL(10,6) NOT NULL,
    thread_id TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX idx_usage_user_date ON usage_logs(user_id, created_at);
```

Provider Router Pattern


Further Considerations
API Key Storage Strategy?



Option A: Environment variables only (secure, requires restart)
Option B: Encrypted in PostgreSQL per-tenant (flexible, complexity)
Recommend: Hybrid — system keys in env, user-provided keys encrypted in DB
Scaling PostgreSQL Checkpoints?

For >1M conversations: Partition by tenant_id hash
For time-series usage: TimescaleDB extension with automatic retention
Consider: Archive old checkpoints to S3 with pg_dump
Real-Time Streaming Architecture?

Current: gRPC streaming works for single-user
Multi-user: Add Redis Pub/Sub for cross-instance message fanout
Consider: WebSocket gateway (Socket.io) with gRPC backend
Cost Allocation Billing?

Simple: Daily aggregation cron → Stripe usage-based billing
Advanced: Real-time metering with Kafka → ClickHouse → dashboards
Recommend: Start with PostgreSQL aggregation, migrate to ClickHouse at scale

---


Reorganized Plan: Configurable Multi-Provider Agent Platform
Based on your session analysis, I've identified your core goals and reorganized the plan into a coherent learning + implementation path.

Session Insights Summary
Theme	Your Goal	Key Quote
Modularity	"Swap, Don't Stack" architecture	"endpoint of the LLM service is independent"
Harness Theory	LLM as harness, not just endpoint	"turns 'LLM endpoint' into 'LLM harness'"
Tool Discipline	Constrain creative capacity in sandboxes	"Precise tool definitions eliminate variance"
Provider Portability	Claude/OpenAI/Local as config, not code	"task-oriented RL tools with understanding of user data"
Learning Path	Technical expertise in system design	"help me understand the technical expertise"
Reorganized Implementation Plan
```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 0: FOUNDATION (You Are Here)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│  ✅ Orchestrator with LangGraph                                             │
│  ✅ Local LLM inference (llama.cpp)                                         │
│  ✅ Tool registry with circuit breakers                                     │
│  ✅ Sandbox execution                                                       │
│  ✅ Basic chat UI                                                           │
│  ❌ Multi-provider support                                                  │
│  ❌ Settings/configuration UI                                               │
│  ❌ Multi-user isolation                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 1: PROVIDER ABSTRACTION                            │
│                         (Technical Foundation)                              │
├─────────────────────────────────────────────────────────────────────────────┤
│  Goal: Make LLM provider swappable without code changes                     │
│                                                                             │
│  1.1 Create Provider Interface                                              │
│      └── shared/providers/base_provider.py                                  │
│          • generate(prompt, config) → str                                   │
│          • generate_stream(prompt, config) → AsyncIterator[str]             │
│          • generate_batch(prompt, n, config) → list[str]                    │
│                                                                             │
│  1.2 Implement Provider Adapters                                            │
│      ├── local_provider.py    (wraps existing LLMClient)                    │
│      ├── anthropic_provider.py (Claude API)                                 │
│      ├── openai_provider.py   (GPT-4, etc.)                                 │
│      ├── gemini_provider.py   (Google)                                      │
│      └── perplexity_provider.py (Sonar search)                              │
│                                                                             │
│  1.3 Provider Registry                                                      │
│      └── shared/providers/registry.py                                       │
│          • register_provider(name, provider_class)                          │
│          • get_provider(name, config) → BaseProvider                        │
│          • list_available() → list[ProviderInfo]                            │
│                                                                             │
│  Learning: Adapter Pattern, Dependency Injection, Interface Segregation     │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 2: SETTINGS SERVICE                                │
│                       (Configuration Backend)                               │
├─────────────────────────────────────────────────────────────────────────────┤
│  Goal: Centralized configuration with persistence                           │
│                                                                             │
│  2.1 Define Settings Proto                                                  │
│      └── shared/proto/settings.proto                                        │
│          service SettingsService {                                          │
│            rpc GetConfig(GetConfigRequest) returns (UserConfig);            │
│            rpc UpdateConfig(UpdateConfigRequest) returns (UserConfig);      │
│            rpc ListProviders(Empty) returns (ProviderList);                 │
│            rpc ListTools(Empty) returns (ToolList);                         │
│            rpc SetToolState(SetToolStateRequest) returns (ToolState);       │
│          }                                                                  │
│                                                                             │
│  2.2 Implement Settings Servicer                                            │
│      └── orchestrator/settings_service.py                                   │
│          • SQLite persistence (extend checkpointing.py)                     │
│          • Hot-reload tool registry                                         │
│          • Provider credential validation                                   │
│                                                                             │
│  2.3 Extend AgentRequest Proto                                              │
│      └── Add optional provider_override, tool_overrides to requests         │
│                                                                             │
│  Learning: gRPC Service Design, Proto Schema Evolution, Config Management   │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 3: CONFIGURATION UI                                │
│                        (User Interface)                                     │
├─────────────────────────────────────────────────────────────────────────────┤
│  Goal: Visual interface for all configuration                               │
│                                                                             │
│  3.1 Settings Page Layout                                                   │
│      └── ui_service/src/app/settings/page.tsx                               │
│          ┌─────────────────────────────────────────────────────────┐        │
│          │  Settings                                    [Save]     │        │
│          ├─────────────────────────────────────────────────────────┤        │
│          │  🤖 LLM Provider                                        │        │
│          │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐     │        │
│          │  │ Local       │  │ Claude      │  │ OpenAI      │     │        │
│          │  │ ✓ Active    │  │ ○ API Key   │  │ ○ API Key   │     │        │
│          │  └─────────────┘  └─────────────┘  └─────────────┘     │        │
│          ├─────────────────────────────────────────────────────────┤        │
│          │  ⚙️ Model Parameters                                    │        │
│          │  Temperature: ──●────────── 0.7                         │        │
│          │  Max Tokens:  ──────●────── 2048                        │        │
│          │  □ Enable Self-Consistency (k=5)                        │        │
│          ├─────────────────────────────────────────────────────────┤        │
│          │  🛠️ Tools                                               │        │
│          │  ☑ web_search     ☑ math_solver                         │        │
│          │  ☑ load_web_page  ☑ execute_code                        │        │
│          │  ☐ perplexity     ☐ claude_direct                       │        │
│          └─────────────────────────────────────────────────────────┘        │
│                                                                             │
│  3.2 Component Structure                                                    │
│      ui_service/src/components/settings/                                    │
│      ├── SettingsPanel.tsx       (container)                                │
│      ├── ProviderCards.tsx       (provider selection grid)                  │
│      ├── ParameterSliders.tsx    (temperature, tokens)                      │
│      ├── ToolToggles.tsx         (tool enable/disable)                      │
│      └── ApiKeyInput.tsx         (masked key entry)                         │
│                                                                             │
│  3.3 State Management                                                       │
│      └── React Context + localStorage persistence                           │
│                                                                             │
│  Learning: React Patterns, Radix UI Components, gRPC-Web Integration        │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 4: PERPLEXITY + MCP INTEGRATION                    │
│                         (Advanced Tools)                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│  Goal: Add Perplexity as both tool AND provider                             │
│                                                                             │
│  4.1 Perplexity as Tool (Immediate)                                         │
│      └── tools/builtin/perplexity_search.py                                 │
│          • Follows web_search.py pattern                                    │
│          • sonar/sonar-pro/sonar-reasoning model selection                  │
│          • Returns citations + sources                                      │
│                                                                             │
│  4.2 Perplexity as Provider (Future)                                        │
│      └── shared/providers/perplexity_provider.py                            │
│          • For when you want Perplexity AS the reasoning engine             │
│          • Different from tool (tool = search, provider = generation)       │
│                                                                             │
│  4.3 MCP Bridge (Phase 1C Completion)                                       │
│      └── Implement @mcp_tool decorator in tools/decorators.py               │
│          • Auto-discover tools from MCP servers                             │
│          • npx perplexity-mcp integration                                   │
│                                                                             │
│  Learning: MCP Protocol, Tool vs Provider distinction, API Integration      │
└─────────────────────────────────────────────────────────────────────────────┘
                                     │
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    PHASE 5: MULTI-USER SCALING                              │
│                      (Production Readiness)                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│  Goal: Support concurrent users with isolation                              │
│                                                                             │
│  5.1 Database Migration: SQLite → PostgreSQL                                │
│      • Row-Level Security (RLS) per tenant                                  │
│      • Partitioned checkpoints table                                        │
│      • Usage tracking for cost allocation                                   │
│                                                                             │
│  5.2 Authentication Layer                                                   │
│      • NextAuth.js in UI                                                    │
│      • gRPC Auth Interceptor                                                │
│      • JWT validation with Redis caching                                    │
│                                                                             │
│  5.3 Session Management                                                     │
│      • Redis for session tokens                                             │
│      • Rate limiting per user                                               │
│      • Quota tracking per organization                                      │
│                                                                             │
│  Learning: Multi-tenancy, RLS, Connection Pooling, Rate Limiting            │
└─────────────────────────────────────────────────────────────────────────────┘
```
Technical Expertise Map
Each phase builds specific system design skills:

Phase	System Design Concept	Code Architecture Pattern
1	Interface Segregation	Adapter Pattern, Factory Method
2	Service Contracts	Protocol Buffers, gRPC Services
3	State Management	React Context, Controlled Components
4	Protocol Integration	MCP, API Gateway Pattern
5	Multi-tenancy	RLS, Connection Pooling, Circuit Breaker
Files to Create (Organized by Phase)
Phase 1: Provider Abstraction
Phase 2: Settings Service
Phase 3: Configuration UI
Phase 4: Perplexity Integration
Immediate Next Steps
Start with Phase 1.1 — Create the provider interface:

Create shared/providers/base_provider.py defining the abstract BaseProvider class
Wrap existing LLMClient as LocalProvider
Update orchestrator to use provider registry instead of direct LLMClient
This unlocks everything else — once providers are swappable, settings UI becomes meaningful, and adding Perplexity/Claude/OpenAI becomes configuration.

Further Considerations
API Key Security Strategy? Phase 3 needs key input — store encrypted in SQLite, or require env vars only? Recommend: UI shows "configured" badge, keys stay in env for security.

Perplexity: Tool or Provider First?

Tool: Search augmentation (like Serper but smarter) — simpler, immediate value
Provider: Full reasoning engine — more complex, requires prompt adaptation
Recommend: Start as tool, add provider later
Skip to Phase 3 UI First? You could build the settings UI with mock data to validate UX before backend, then wire up real providers. Faster iteration loop.

---

```

```
Decoupled Microservice Architecture with Clawdbot Entry Point
Design a loosely-coupled, event-driven architecture where Clawdbot acts as the input gateway, services communicate via message contracts (not direct dependencies), and the provider layer uses OpenAI-compatible API standard for extensibility to Unreal Engine, DAWs, and other systems.

Core Design Principles
Principle	Implementation	Benefit
Contract-First	All services communicate via Protocol Buffers or OpenAI-compatible JSON	Services replaceable without code changes
Event-Driven	Message bus (Redis Streams) for async communication	No direct service-to-service coupling
Adapter Pattern	Each external system gets an adapter, not direct integration	Swap Clawdbot for Unreal without touching core
Single Responsibility	Each service does ONE thing well	Independent scaling and deployment
OpenAI-Compatible	Online providers follow /v1/chat/completions standard	Add any LLM provider as configuration
UML Component Diagram
```
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    ENTRY ADAPTERS                                        │
│                        (Interchangeable Input Sources)                                   │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐         │
│   │  Clawdbot    │    │  Next.js UI  │    │   Unreal     │    │   Ableton    │         │
│   │  Adapter     │    │  Adapter     │    │   Adapter    │    │   Adapter    │         │
│   │              │    │              │    │  (Future)    │    │  (Future)    │         │
│   │ Telegram/    │    │ WebSocket/   │    │ Subsystem/   │    │ Max4Live/    │         │
│   │ Discord/etc  │    │ REST         │    │ Delegate     │    │ OSC          │         │
│   └──────┬───────┘    └──────┬───────┘    └──────┬───────┘    └──────┬───────┘         │
│          │                   │                   │                   │                  │
│          │    «implements»   │    «implements»   │    «implements»   │                  │
│          ▼                   ▼                   ▼                   ▼                  │
│   ┌─────────────────────────────────────────────────────────────────────────────┐      │
│   │                        <<interface>> IInputAdapter                           │      │
│   │  + sendMessage(context: Context, message: str) → RequestId                   │      │
│   │  + receiveResponse(requestId: RequestId) → AsyncStream<Response>             │      │
│   │  + getCapabilities() → AdapterCapabilities                                   │      │
│   └─────────────────────────────────────────────────────────────────────────────┘      │
│                                          │                                              │
└──────────────────────────────────────────┼──────────────────────────────────────────────┘
                                           │
                                           ▼
┌─────────────────────────────────────────────────────────────────────────────────────────┐
│                                    MESSAGE BUS                                           │
│                         (Event-Driven Decoupling Layer)                                  │
├─────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                          │
│   ┌─────────────────────────────────────────────────────────────────────────────┐      │
│   │                         Redis Streams / Event Bus                            │      │
│   │                                                                              │      │
│   │   Channels:                                                                  │      │
│   │   ├── requests.incoming     (adapters → orchestrator)                        │      │
│   │   ├── requests.processed    (orchestrator → adapters)                        │      │
│   │   ├── tools.execute         (orchestrator → tool workers)                    │      │
│   │   ├── tools.results         (tool workers → orchestrator)                    │      │
│   │   ├── inference.request     (orchestrator → provider router)                 │      │
│   │   └── inference.response    (provider router → orchestrator)                 │      │
│   │                                                                              │      │
│   │   Message Format: { id, type, payload, metadata, timestamp, correlation_id } │      │
│   └─────────────────────────────────────────────────────────────────────────────┘      │
│                                                                                          │
└───────────┬─────────────────────────┬─────────────────────────┬──────────────────────────┘
            │                         │                         │
            ▼                         ▼                         ▼
┌───────────────────────┐ ┌───────────────────────┐ ┌───────────────────────────────────┐
│   ORCHESTRATOR        │ │   TOOL EXECUTOR       │ │   PROVIDER ROUTER                 │
│   SERVICE             │ │   SERVICE             │ │   SERVICE                         │
├───────────────────────┤ ├───────────────────────┤ ├───────────────────────────────────┤
│                       │ │                       │ │                                   │
│ • LangGraph State     │ │ • Tool Registry       │ │ • Provider Registry               │
│   Machine             │ │ • Circuit Breakers    │ │ • OpenAI-Compatible               │
│ • Checkpointing       │ │ • Sandbox Execution   │ │   Interface                       │
│ • Context Management  │ │ • MCP Bridge          │ │ • Fallback Logic                  │
│ • Self-Consistency    │ │                       │ │                                   │
│                       │ │ Subscribes:           │ │ Subscribes:                       │
│ Subscribes:           │ │  tools.execute        │ │  inference.request                │
│  requests.incoming    │ │                       │ │                                   │
│  tools.results        │ │ Publishes:            │ │ Publishes:                        │
│  inference.response   │ │  tools.results        │ │  inference.response               │
│                       │ │                       │ │                                   │
│ Publishes:            │ └───────────┬───────────┘ └─────────────┬─────────────────────┘
│  requests.processed   │             │                           │
│  tools.execute        │             ▼                           ▼
│  inference.request    │ ┌───────────────────────┐ ┌───────────────────────────────────┐
│                       │ │   TOOL WORKERS        │ │   PROVIDER LAYER                  │
└───────────────────────┘ ├───────────────────────┤ ├───────────────────────────────────┤
                          │                       │ │                                   │
                          │ ┌─────────────────┐   │ │ ┌─────────────────────────────┐   │
                          │ │ SandboxWorker   │   │ │ │  <<abstract>>               │   │
                          │ │ (code exec)     │   │ │ │  BaseProvider               │   │
                          │ └─────────────────┘   │ │ │  + generate(req) → resp     │   │
                          │ ┌─────────────────┐   │ │ │  + stream(req) → stream     │   │
                          │ │ SearchWorker    │   │ │ │  + get_models() → list      │   │
                          │ │ (web/perplexity)│   │ │ └──────────┬──────────────────┘   │
                          │ └─────────────────┘   │ │            │                      │
                          │ ┌─────────────────┐   │ │    ┌───────┴───────┐              │
                          │ │ RAGWorker       │   │ │    │               │              │
                          │ │ (chroma)        │   │ │    ▼               ▼              │
                          │ └─────────────────┘   │ │ ┌─────────┐  ┌───────────────┐    │
                          │ ┌─────────────────┐   │ │ │ Local   │  │ Online        │    │
                          │ │ MCPBridge       │   │ │ │ Provider│  │ Provider      │    │
                          │ │ (future tools)  │   │ │ │         │  │               │    │
                          │ └─────────────────┘   │ │ │ llama   │  │ OpenAI-compat │    │
                          │                       │ │ │ .cpp    │  │ REST API      │    │
                          └───────────────────────┘ │ └─────────┘  └───────┬───────┘    │
                                                    │                      │            │
                                                    │              ┌───────┴───────┐    │
                                                    │              │               │    │
                                                    │              ▼               ▼    │
                                                    │        ┌──────────┐  ┌──────────┐│
                                                    │        │ Claude   │  │Perplexity││
                                                    │        │ Anthropic│  │ Sonar    ││
                                                    │        └──────────┘  └──────────┘│
                                                    │        ┌──────────┐  ┌──────────┐│
                                                    │        │ OpenAI   │  │ Gemini   ││
                                                    │        │ GPT-4    │  │ Google   ││
                                                    │        └──────────┘  └──────────┘│
                                                    └───────────────────────────────────┘
```

UML Sequence Diagram: Request Flow
```
┌─────────┐  ┌───────────┐  ┌───────────┐  ┌────────────┐  ┌─────────────┐  ┌──────────┐
│Clawdbot │  │  Message  │  │Orchestrator│  │   Tool     │  │  Provider   │  │  Online  │
│ Adapter │  │   Bus     │  │  Service   │  │  Executor  │  │   Router    │  │ Provider │
└────┬────┘  └─────┬─────┘  └─────┬──────┘  └──────┬─────┘  └──────┬──────┘  └────┬─────┘
     │             │              │                │               │              │
     │ publish     │              │                │               │              │
     │ (requests.  │              │                │               │              │
     │  incoming)  │              │                │               │              │
     │────────────>│              │                │               │              │
     │             │              │                │               │              │
     │             │ subscribe    │                │               │              │
     │             │ (requests.   │                │               │              │
     │             │  incoming)   │                │               │              │
     │             │─────────────>│                │               │              │
     │             │              │                │               │              │
     │             │              │ LangGraph      │               │              │
     │             │              │ llm_node       │               │              │
     │             │              │────┐           │               │              │
     │             │              │    │ prepare   │               │              │
     │             │              │<───┘ prompt    │               │              │
     │             │              │                │               │              │
     │             │              │ publish        │               │              │
     │             │              │ (inference.    │               │              │
     │             │              │  request)      │               │              │
     │             │<─────────────│                │               │              │
     │             │              │                │               │              │
     │             │              │                │  subscribe    │              │
     │             │              │                │  (inference.  │              │
     │             │              │                │   request)    │              │
     │             │─────────────────────────────────────────────>│              │
     │             │              │                │               │              │
     │             │              │                │               │ route to     │
     │             │              │                │               │ provider     │
     │             │              │                │               │─────────────>│
     │             │              │                │               │              │
     │             │              │                │               │   OpenAI-    │
     │             │              │                │               │   compat     │
     │             │              │                │               │   response   │
     │             │              │                │               │<─────────────│
     │             │              │                │               │              │
     │             │              │                │  publish      │              │
     │             │              │                │  (inference.  │              │
     │             │              │                │   response)   │              │
     │             │<────────────────────────────────────────────│              │
     │             │              │                │               │              │
     │             │ subscribe    │                │               │              │
     │             │ (inference.  │                │               │              │
     │             │  response)   │                │               │              │
     │             │─────────────>│                │               │              │
     │             │              │                │               │              │
     │             │              │ tool_call      │               │              │
     │             │              │ detected?      │               │              │
     │             │              │────┐           │               │              │
     │             │              │    │ yes       │               │              │
     │             │              │<───┘           │               │              │
     │             │              │                │               │              │
     │             │              │ publish        │               │              │
     │             │              │ (tools.execute)│               │              │
     │             │<─────────────│                │               │              │
     │             │              │                │               │              │
     │             │              │                │ subscribe     │              │
     │             │              │                │ (tools.       │              │
     │             │              │                │  execute)     │              │
     │             │─────────────────────────────>│               │              │
     │             │              │                │               │              │
     │             │              │                │ execute       │              │
     │             │              │                │ (sandbox/     │              │
     │             │              │                │  search/etc)  │              │
     │             │              │                │───┐           │              │
     │             │              │                │   │           │              │
     │             │              │                │<──┘           │              │
     │             │              │                │               │              │
     │             │              │                │ publish       │              │
     │             │              │                │ (tools.       │              │
     │             │              │                │  results)     │              │
     │             │<────────────────────────────│               │              │
     │             │              │                │               │              │
     │             │ subscribe    │                │               │              │
     │             │ (tools.      │                │               │              │
     │             │  results)    │                │               │              │
     │             │─────────────>│                │               │              │
     │             │              │                │               │              │
     │             │              │ [loop until    │               │              │
     │             │              │  final answer] │               │              │
     │             │              │                │               │              │
     │             │              │ publish        │               │              │
     │             │              │ (requests.     │               │              │
     │             │              │  processed)    │               │              │
     │             │<─────────────│                │               │              │
     │             │              │                │               │              │
     │ subscribe   │              │                │               │              │
     │ (requests.  │              │                │               │              │
     │  processed) │              │                │               │              │
     │<────────────│              │                │               │              │
     │             │              │                │               │              │
     │ send to     │              │                │               │              │
     │ user        │              │                │               │              │
     ▼             │              │                │               │              │
```

UML Class Diagram: Provider Abstraction

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              PROVIDER LAYER                                  │
│                    (OpenAI-Compatible API Standard)                          │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │        <<abstract>>                 │
                    │        BaseProvider                 │
                    ├─────────────────────────────────────┤
                    │ - name: str                         │
                    │ - config: ProviderConfig            │
                    │ - circuit_breaker: CircuitBreaker   │
                    ├─────────────────────────────────────┤
                    │ + generate(request: ChatRequest)    │
                    │     → ChatResponse                  │
                    │ + generate_stream(request)          │
                    │     → AsyncIterator[ChatChunk]      │
                    │ + get_models() → list[ModelInfo]    │
                    │ + health_check() → bool             │
                    │ # _normalize_response(raw) → Chat   │
                    │ # _handle_error(e) → ProviderError  │
                    └──────────────┬──────────────────────┘
                                   │
                                   │ extends
                    ┌──────────────┴──────────────┐
                    │                             │
                    ▼                             ▼
┌─────────────────────────────────┐  ┌─────────────────────────────────────┐
│        LocalProvider            │  │         OnlineProvider              │
├─────────────────────────────────┤  │         <<abstract>>                │
│ - grpc_client: LLMClient        │  ├─────────────────────────────────────┤
│ - model_path: str               │  │ - base_url: str                     │
│                                 │  │ - api_key: str                      │
├─────────────────────────────────┤  │ - http_client: AsyncHTTPClient      │
│ + generate(request)             │  │ - timeout: int                      │
│   → forwards to llama.cpp       │  ├─────────────────────────────────────┤
│     via gRPC                    │  │ + generate(request)                 │
│                                 │  │   → POST /v1/chat/completions       │
│ + generate_stream(request)      │  │                                     │
│   → gRPC streaming              │  │ + generate_stream(request)          │
│                                 │  │   → SSE stream                      │
│ + get_models()                  │  │                                     │
│   → returns loaded model        │  │ # _build_headers() → dict           │
└─────────────────────────────────┘  │ # _build_payload(req) → dict        │
                                     └──────────────┬──────────────────────┘
                                                    │
                                                    │ extends
                    ┌───────────────┬───────────────┼───────────────┬───────────────┐
                    │               │               │               │               │
                    ▼               ▼               ▼               ▼               ▼
           ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐
           │  OpenAI    │  │ Anthropic  │  │ Perplexity │  │  Gemini    │  │  Ollama    │
           │  Provider  │  │ Provider   │  │ Provider   │  │  Provider  │  │  Provider  │
           ├────────────┤  ├────────────┤  ├────────────┤  ├────────────┤  ├────────────┤
           │base_url:   │  │base_url:   │  │base_url:   │  │base_url:   │  │base_url:   │
           │api.openai  │  │api.anthropic│ │api.perplexity│ │generative  │  │localhost:  │
           │.com/v1     │  │.com/v1     │  │.ai/        │  │language    │  │11434/v1    │
           │            │  │            │  │            │  │.googleapis │  │            │
           │models:     │  │models:     │  │models:     │  │.com/v1     │  │models:     │
           │- gpt-4o    │  │- claude-4  │  │- sonar     │  │            │  │- llama3    │
           │- gpt-4     │  │- claude-3.5│  │- sonar-pro │  │models:     │  │- mistral   │
           │- o3        │  │- claude-3  │  │- sonar-    │  │- gemini-2  │  │- qwen      │
           │            │  │            │  │  reasoning │  │- gemini-1.5│  │            │
           └────────────┘  └────────────┘  └────────────┘  └────────────┘  └────────────┘

                            All use OpenAI-compatible:
                            POST /v1/chat/completions
                            {
                              "model": "...",
                              "messages": [...],
                              "temperature": 0.7,
                              "max_tokens": 2048,
                              "stream": true/false,
                              "tools": [...] (function calling)
                            }
```
UML Class Diagram: Adapter Pattern for Entry Points

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              ADAPTER LAYER                                   │
│                    (Interchangeable Entry Points)                            │
└─────────────────────────────────────────────────────────────────────────────┘

                    ┌─────────────────────────────────────┐
                    │        <<interface>>                │
                    │        IInputAdapter                │
                    ├─────────────────────────────────────┤
                    │ + connect() → void                  │
                    │ + disconnect() → void               │
                    │ + on_message(callback) → void       │
                    │ + send_response(ctx, msg) → void    │
                    │ + get_context(raw) → Context        │
                    │ + get_capabilities() → Capabilities │
                    └──────────────┬──────────────────────┘
                                   │
           ┌───────────────┬───────┴───────┬───────────────┬───────────────┐
           │               │               │               │               │
           ▼               ▼               ▼               ▼               ▼
┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐
│ ClawdbotAdapter  │ │ WebUIAdapter     │ │ UnrealAdapter    │ │ DAWAdapter       │
├──────────────────┤ ├──────────────────┤ ├──────────────────┤ ├──────────────────┤
│                  │ │                  │ │ (Future)         │ │ (Future)         │
│ Protocol:        │ │ Protocol:        │ │                  │ │                  │
│ - Telegram Bot   │ │ - WebSocket      │ │ Protocol:        │ │ Protocol:        │
│ - Discord Bot    │ │ - REST API       │ │ - Unreal         │ │ - OSC            │
│ - WhatsApp       │ │ - gRPC-Web       │ │   Subsystem      │ │ - MIDI           │
│                  │ │                  │ │ - Blueprint      │ │ - Max4Live       │
│ Features:        │ │ Features:        │ │   Delegates      │ │                  │
│ - Multi-channel  │ │ - Settings UI    │ │ - C++ Interface  │ │ Features:        │
│ - User sessions  │ │ - Real-time      │ │                  │ │ - Ableton Live   │
│ - Skills routing │ │   streaming      │ │ Features:        │ │ - Logic Pro      │
│                  │ │                  │ │ - Game state     │ │ - Houdini        │
└──────────────────┘ └──────────────────┘ │ - NPC dialogue   │ │                  │
                                          │ - Procedural     │ │                  │
                                          │   generation     │ └──────────────────┘
                                          └──────────────────┘

                    ┌─────────────────────────────────────┐
                    │        <<interface>>                │
                    │        IOutputAdapter               │
                    ├─────────────────────────────────────┤
                    │ + send(ctx, message) → void         │
                    │ + stream(ctx, chunks) → void        │
                    │ + notify(ctx, event) → void         │
                    └─────────────────────────────────────┘
```
Files to Create (Simplified Structure)
```
shared/
├── bus/
│   ├── __init__.py
│   ├── message_bus.py          # Redis Streams abstraction
│   ├── channels.py             # Channel name constants
│   └── message.py              # Message dataclass
│
├── providers/
│   ├── __init__.py
│   ├── base_provider.py        # Abstract base class
│   ├── local_provider.py       # Wraps LLMClient (llama.cpp)
│   └── online_provider.py      # OpenAI-compatible REST
│       # Subclasses created via config, not code:
│       # - anthropic: base_url=api.anthropic.com, model=claude-*
│       # - openai: base_url=api.openai.com, model=gpt-*
│       # - perplexity: base_url=api.perplexity.ai, model=sonar-*
│
├── adapters/
│   ├── __init__.py
│   ├── base_adapter.py         # IInputAdapter interface
│   ├── clawdbot_adapter.py     # Clawdbot integration
│   ├── webui_adapter.py        # Next.js UI
│   └── grpc_adapter.py         # Direct gRPC clients
│
└── contracts/
    ├── messages.py             # Shared message types
    └── context.py              # Request context
```
Configuration-Driven Providers (Not Code)
```
# config/providers.yaml
providers:
  local:
    type: local
    grpc_host: llm_service
    grpc_port: 50051
    default_model: qwen2.5-3b-instruct
    
  claude:
    type: online
    base_url: https://api.anthropic.com/v1
    api_key_env: ANTHROPIC_API_KEY
    models:
      - claude-sonnet-4-20250514
      - claude-3-5-sonnet-20241022
      
  openai:
    type: online
    base_url: https://api.openai.com/v1
    api_key_env: OPENAI_API_KEY
    models:
      - gpt-4o
      - o3
      
  perplexity:
    type: online
    base_url: https://api.perplexity.ai
    api_key_env: PERPLEXITY_API_KEY
    models:
      - sonar
      - sonar-pro
      - sonar-reasoning
      
  ollama:
    type: online
    base_url: http://localhost:11434/v1
    api_key_env: null  # No key needed
    models:
      - llama3.2
      - mistral
```

# Further Considerations
Message Bus Technology?

Redis Streams (recommended): Simple, fast, already in stack
Kafka: For extreme scale (>100k msg/s)
RabbitMQ: If complex routing needed
Clawdbot Integration Depth?

Shallow: Clawdbot as pure I/O adapter, all logic in orchestrator
Deep: Use Clawdbot's skills system, harness provides tools only
Recommend: Shallow — your orchestrator is more capable
Unreal Engine Protocol?

Option A: gRPC plugin (complex, performant)
Option B: REST/WebSocket (simpler, slight latency)
Option C: Shared memory / Named pipes (fastest, platform-specific)
Recommend: WebSocket for prototyping, gRPC for production
DAW Integration Protocol?

OSC (Open Sound Control): Universal, Ableton/Logic/Houdini support
Max4Live: Ableton-specific, deepest integration
Recommend: OSC adapter that speaks to multiple DAWs

</details>
