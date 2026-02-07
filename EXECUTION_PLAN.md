# Parallel Execution Plan - High Priority Actions

> **Created**: February 3, 2026  
> **Purpose**: Actionable parallel execution plan mapping P0/P1 tasks to skill personas

---

## Overview

This plan organizes high-priority work into **5 parallel tracks** that can be executed simultaneously by agents with different skill profiles. Each track is independent with clear interfaces.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                      PARALLEL EXECUTION TRACKS                               │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Track A (SRE)          Track B (LLM)        Track C (Integration)          │
│  ───────────────        ─────────────        ──────────────────────         │
│  │ Health Checks │      │ Self-Consist│      │ Real Adapters   │           │
│  │ PostgreSQL    │      │ Tool Parsing│      │ OAuth Flows     │           │
│  │ Rate Limiting │      │ Evals       │      │ MCP Bridge      │           │
│  └───────────────┘      └─────────────┘      └─────────────────┘           │
│                                                                              │
│  Track D (State)        Track E (Network)                                   │
│  ───────────────        ─────────────────                                   │
│  │ Checkpointing │      │ Service Mesh │                                    │
│  │ Crash Recovery│      │ gRPC Health  │                                    │
│  │ WAL Flushing  │      │ DNS/Ports    │                                    │
│  └───────────────┘      └──────────────┘                                    │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Track A: Infrastructure & Reliability
**Skill File**: `.claude/SKILLS/systems_engineer_sre.md`  
**Priority**: P0-P1  
**Dependencies**: None (foundational)

### Tasks

#### A1. Fix Health Checks (P0) ⏱️ 2h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `docker-compose.yaml`, all `*/Dockerfile`

```bash
# Verification command
make grpc-health
```

**Completed**:
- [x] Installed `grpc_health_probe` in all gRPC service Dockerfiles
- [x] All services report healthy within 30s of startup
- [x] Added `make grpc-health` Makefile target for health verification
- [x] Rebuilt all gRPC services with health probe support

---

#### A2. Rate Limiting Implementation (P0) ⏱️ 3h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `shared/utils/rate_limiter.py`, `shared/providers/registry.py`

**Completed**:
- [x] Created `shared/utils/rate_limiter.py` with TokenBucketRateLimiter
- [x] Integrated rate limiting into ProviderRegistry.get_provider()
- [x] Added RateLimitExceeded exception with retry-after support
- [x] Per-provider default rate limits configured

---

#### A3. PostgreSQL Migration (P1) ⏱️ 4h
**Status**: Not Started  
**Files**: `core/checkpointing.py`, `docker-compose.yaml`

**Acceptance Criteria**:
- [ ] Checkpoints stored in PostgreSQL
- [ ] Connection pooling with asyncpg
- [ ] Migration script from SQLite

**Actions**:
1. Add `postgres` service to `docker-compose.yaml`
2. Create `shared/database/` module with connection pool
3. Update `Checkpointer` to use PostgreSQL driver
4. Create migration script: `tools/migrate_sqlite_to_pg.py`

---

## Track B: LLM/AI Reliability
**Skill File**: `.claude/SKILLS/llm_ai_engineer.md`  
**Priority**: P0-P1  
**Dependencies**: None

### Tasks

#### B1. Self-Consistency Integration (P0) ⏱️ 3h
**Status**: ✅ COMPLETED (Already Implemented)  
**Files**: `core/self_consistency.py`, `orchestrator/orchestrator_service.py`, `orchestrator/config.py`

**Already Implemented**:
- [x] `SelfConsistencyVerifier` class in core/self_consistency.py
- [x] Wired into orchestrator initialization (line 764-771)
- [x] Configurable via environment variables:
  - `ENABLE_SELF_CONSISTENCY=true` (default: false)
  - `SELF_CONSISTENCY_SAMPLES=5` (default: 5)
  - `SELF_CONSISTENCY_THRESHOLD=0.6` (default: 0.6)
- [x] Multi-sample voting with majority answer extraction
- [x] Uncertainty score available via `consistency_score`

**To Enable**: Set `ENABLE_SELF_CONSISTENCY=true` in docker-compose.yaml or .env

---

#### B2. Tool-Calling JSON Parser Consolidation (P0) ⏱️ 2h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `shared/utils/json_parser.py`, `orchestrator/orchestrator_service.py`

**Completed**:
- [x] `shared/utils/json_parser.py` already exists with robust extraction
- [x] Handles: raw JSON, fenced JSON (```json), JSON + prose, nested JSON
- [x] Integrated `extract_tool_json()` and `safe_parse_arguments()` into orchestrator
- [x] Removed 40+ lines of duplicated inline JSON parsing
- [x] Added `_normalize_json_booleans()` for Python→JSON boolean conversion

---

#### B3. Multi-Step Query Guardrails (P1) ⏱️ 2h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `orchestrator/intent_patterns.py`, `orchestrator/orchestrator_service.py`

**Completed**:
- [x] Added `MULTI_TOOL_INTENTS` to `intent_patterns.py`
- [x] Implemented `analyze_intent()` function with `IntentAnalysis` dataclass
- [x] Added `DESTINATION_ALIASES` for location resolution
- [x] Integrated intent analysis into orchestrator's `_process_query()`
- [x] Returns clarifying questions when destination is ambiguous

---

#### B4. Eval Framework Setup (P1) ⏱️ 3h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `tests/evals/` (NEW)

**Completed**:
- [x] Created `tests/evals/` directory structure
- [x] Created `tests/evals/eval_runner.py` with YAML-based test cases
- [x] Created `tests/evals/tool_selection_cases.yaml` with 20+ eval cases
- [x] Defined eval metrics: tool_selection_accuracy, argument_correctness
- [x] Added `make eval`, `make eval-quick`, `make eval-report` targets
- [x] Cases organized by difficulty: easy, medium, hard
- [x] Includes negative cases and edge cases

**Usage**:
```bash
make eval          # Run all evals
make eval-quick    # Run easy cases only
make eval-report   # Generate JSON report
```

---

## Track C: Integration & Adapters
**Skill File**: `.claude/SKILLS/integration_expert.md`  
**Priority**: P1  
**Dependencies**: Track A (health checks)

### Tasks

#### C1. Google Calendar OAuth Adapter (P1) ⏱️ 4h
**Status**: Not Started  
**Files**: `shared/adapters/calendar/google.py` (NEW)

**Acceptance Criteria**:
- [ ] OAuth 2.0 flow with refresh token
- [ ] Fetch events → `CalendarEvent` canonical schema
- [ ] Integration test with mock Google API

**Actions**:
1. Create `shared/adapters/calendar/google.py`:
   ```python
   class GoogleCalendarAdapter(CalendarAdapter):
       async def authenticate(self, auth_code: str) -> TokenPair: ...
       async def fetch_events(self, start: datetime, end: datetime) -> List[CalendarEvent]: ...
   ```
2. Add OAuth callback route to UI service
3. Store refresh tokens encrypted in settings

---

#### C2. MCP Bridge Enhancement (P1) ⏱️ 3h
**Status**: Implemented, needs hardening  
**Files**: `bridge_service/mcp_server.py`

**Acceptance Criteria**:
- [ ] All 8 tools have request/response validation
- [ ] Rate limiting per tool (configurable)
- [ ] Error responses follow MCP spec

**Actions**:
1. Add Pydantic validation to all tool handlers
2. Implement per-tool rate limits in config
3. Add MCP-compliant error codes and messages

---

#### C3. Finance Adapter (Plaid) (P1) ⏱️ 4h
**Status**: Not Started  
**Files**: `shared/adapters/finance/plaid.py` (NEW)

**Acceptance Criteria**:
- [ ] Plaid Link integration for account connection
- [ ] Transaction fetch → `FinancialTransaction` canonical
- [ ] Balance fetch → `FinancialAccount` canonical

**Actions**:
1. Create Plaid adapter following adapter protocol
2. Add Plaid Link webhook handler
3. Integration test with Plaid sandbox

---

## Track D: State Management & Orchestration
**Skill File**: `.claude/SKILLS/orchestrator_state_engineer.md`  
**Priority**: P0-P1  
**Dependencies**: Track A (PostgreSQL for full implementation)

### Tasks

#### D1. Crash Recovery Testing (P0) ⏱️ 2h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `core/checkpointing.py`, `tests/integration/test_crash_resume.py`, `tools/base.py`

**Completed**:
- [x] `CheckpointManager.scan_for_crashed_threads()` validated
- [x] `RecoveryManager` initialization verified
- [x] `validate_checkpoint_integrity()` working
- [x] Fixed `test_crash_resume.py` import (DockerComposeManager alias)
- [x] Idempotency prevents duplicate tool executions on resume
- [x] `@idempotent` decorator validated with cache stats

**Verification**:
```bash
docker exec orchestrator python -c "
from core.checkpointing import CheckpointManager, RecoveryManager
from tools.base import idempotent, get_idempotency_cache
# All imports and basic operations work
"
```

---

#### D2. LangGraph State Validation (P1) ⏱️ 2h
**Status**: ✅ COMPLETED (Already Implemented)  
**Files**: `core/state.py`, `core/graph.py`

**Already Implemented**:
- [x] Pydantic models for `WorkflowConfig`, `ModelConfig`, `ToolExecutionResult`
- [x] `AgentState` TypedDict with annotated reducers
- [x] `create_initial_state()` factory function
- [x] Field validation with `ge`, `le`, `Literal` constraints
- [x] Immutable configs via `frozen = True`

---

#### D3. Idempotency Keys for Tools (P1) ⏱️ 3h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `tools/base.py`

**Completed**:
- [x] Added `compute_idempotency_key(tool_name, args)` function
- [x] Created `IdempotencyCache` class with TTL support (5 min default)
- [x] Added `@idempotent` decorator for tool functions
- [x] Thread-safe implementation with cache eviction

---

## Track E: Network & Service Mesh
**Skill File**: `.claude/SKILLS/network_engineer.md`  
**Priority**: P1  
**Dependencies**: Track A (health checks)

### Tasks

#### E1. gRPC Reflection Health (P1) ⏱️ 1h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: All `*_service.py` files, `Makefile`

**Completed**:
- [x] All gRPC services have health servicers registered
- [x] `grpc_health_probe` installed in all containers
- [x] Added `make grpc-health` target for verification
- [x] All services report healthy via `docker compose ps`

---

#### E2. Service Discovery Documentation (P1) ⏱️ 1h
**Status**: ✅ COMPLETED (Feb 3, 2026)  
**Files**: `RUNBOOK_DOCKER.md`

**Completed**:
- [x] Added network map table: service → port → protocol → health check
- [x] Added DNS resolution guide with container-to-container examples
- [x] Documented troubleshooting commands (network inspect, DNS tests, gRPC health)
- [x] Added gRPC reflection discovery commands

---

## Dependency Graph

```
                    ┌─────────────────┐
                    │   Track A (SRE) │
                    │  Health Checks  │
                    │  Rate Limiting  │
                    │  PostgreSQL     │
                    └────────┬────────┘
                             │
         ┌───────────────────┼───────────────────┐
         │                   │                   │
         ▼                   ▼                   ▼
┌─────────────────┐ ┌─────────────────┐ ┌─────────────────┐
│  Track B (LLM)  │ │ Track C (Integ) │ │  Track D (State)│
│ Self-Consistency│ │ OAuth Adapters  │ │ Crash Recovery  │
│ JSON Parsing    │ │ MCP Hardening   │ │ Idempotency     │
└─────────────────┘ └─────────────────┘ └─────────────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │ Track E (Network)│
                    │ gRPC Health     │
                    │ Documentation   │
                    └─────────────────┘
```

**Parallelization Strategy**:
- **Phase 1 (Immediate)**: Track A, Track B, Track D can start in parallel
- **Phase 2 (After A1 done)**: Track C, Track E can start
- **Phase 3 (Integration)**: Cross-track integration testing

---

## Execution Commands

### Start All Tracks (Parallel)

```bash
# Terminal 1 - Track A (SRE)
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm
# Follow EXECUTION_PLAN.md Track A tasks

# Terminal 2 - Track B (LLM)  
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm
# Follow EXECUTION_PLAN.md Track B tasks

# Terminal 3 - Track D (State)
cd /Users/sertanavdan/Documents/Software/AI/gRPC_llm
# Follow EXECUTION_PLAN.md Track D tasks
```

### Verification After Each Track

```bash
# Health check all services
make health

# Run integration tests
make test-integration

# Check observability
curl http://localhost:8100/metrics
```

---

## Progress Tracking

| Track | Task | Owner | Status | ETA |
|-------|------|-------|--------|-----|
| A | A1. Health Checks | SRE Agent | ✅ | Done |
| A | A2. Rate Limiting | SRE Agent | ✅ | Done |
| A | A3. PostgreSQL | SRE Agent | ⬜ | 4h |
| B | B1. Self-Consistency | LLM Agent | ✅ | Done |
| B | B2. JSON Parser | LLM Agent | ✅ | Done |
| B | B3. Multi-Step Guards | LLM Agent | ✅ | Done |
| B | B4. Eval Framework | LLM Agent | ✅ | Done |
| C | C1. Google Calendar | Integration Agent | ⬜ | 4h |
| C | C2. MCP Hardening | Integration Agent | ⬜ | 3h |
| C | C3. Plaid Finance | Integration Agent | ⬜ | 4h |
| D | D1. Crash Recovery | State Agent | ✅ | Done |
| D | D2. State Validation | State Agent | ✅ | Done |
| D | D3. Idempotency Keys | State Agent | ✅ | Done |
| E | E1. gRPC Health | Network Agent | ✅ | Done |
| E | E2. Documentation | Network Agent | ✅ | Done |

---

## Success Metrics

### P0 Completion Criteria
- [x] All services report healthy in `docker compose ps`
- [x] Rate limiting prevents provider abuse
- [x] Crash recovery validated with idempotency
- [x] Self-consistency confidence available via config flag
- [x] Tool JSON parsing handles all known failure modes

### P1 Completion Criteria
- [ ] At least 1 real adapter (Google Calendar or Plaid) working
- [ ] MCP bridge passes all validation tests
- [x] Eval framework running with `make eval`
- [x] gRPC health checks work for all services
- [x] Network documentation complete

---

## Quick Reference: Which Skill for Which Task?

| Task Category | Skill File | Example Tasks |
|---------------|------------|---------------|
| Docker, health checks, PostgreSQL | `systems_engineer_sre.md` | A1, A2, A3 |
| Tool calling, JSON parsing, evals | `llm_ai_engineer.md` | B1, B2, B3, B4 |
| OAuth, adapters, MCP protocol | `integration_expert.md` | C1, C2, C3 |
| State machines, checkpointing | `orchestrator_state_engineer.md` | D1, D2, D3 |
| gRPC, DNS, ports | `network_engineer.md` | E1, E2 |
| Prioritization, metrics, UX | `product_manager.md` | Planning, success criteria |
