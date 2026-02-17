# NEXUS — Current State

> **GSD Canonical File** | Updated 2026-02-17

---

## Current Phase

**Phase 6 (UX/UI Visual Expansion)** — **complete**. 4/4 plans executed.

**Progress**: Phase 5 complete (4/4 plans, 98+ new tests, zero regressions). Phase 6 complete (4/4 plans: capability contract, dashboard + adapter cards, finance dashboard + chat actions, monitoring + error taxonomy + preferences).
**Current Focus**: Phase 6 complete. Ready for Phase 7 (Audit Trail).

---

## What's Done

### Track A: Self-Evolving Module Infrastructure
- **A1 ✅** Module manifest schema, dynamic loader (`importlib`), SQLite registry
- **A2 ✅** Fernet credential store with encryption at rest
- **A3 ✅** Agent tool wiring active in orchestrator (`build_module`, `repair_module`, `install_module` registered)
- **A4 ✅** LLM-driven module builder repair stage calls `gateway.generate(purpose=REPAIR)` and records repair attempts

### Track B: Observability & Control
- **B1 ✅** Prometheus metrics, `ModuleMetrics` dataclass
- **B2 ✅** Admin API v1 (routing config hot-reload)
- **B3 ✅** Admin API v2 (module CRUD, credentials management)
- **B4 ✅** Pipeline UI with SSE streaming, React Flow visualization

### Completed Integrations
- ✅ OpenWeather API (weather)
- ✅ Google Calendar OAuth2 (calendar)
- ✅ Clash Royale API (gaming)
- ✅ CIBC CSV files (finance)
- ✅ Showroom metrics demo (test)

### Phase 1: Auth Boundary ✅
- ✅ API key authentication (SHA-256 hashed, SQLite-backed `APIKeyStore`)
- ✅ RBAC enforcement (viewer/operator/admin/owner permission matrix)
- ✅ Auth middleware wired into Admin API (:8003) and Dashboard API (:8001)
- ✅ Org-scoped data isolation (`org_id` in AgentState, ModuleRegistry, CredentialStore)
- ✅ Bootstrap endpoint for initial key creation
- ✅ API key management endpoints (create/list/revoke/rotate)
- ✅ Auth test suite (`make auth-test`)

### Phase 2: Run-Unit Metering ✅
- ✅ `shared/billing/` package (calculator, usage store, quota manager)
- ✅ Tool-call metering wired into `core/graph.py` with fail-open writes
- ✅ Quota enforcement wired into orchestrator request processing
- ✅ Billing admin endpoints (`/admin/billing/usage`, `/admin/billing/usage/history`, `/admin/billing/quota`)
- ✅ Run-unit metrics exported (`nexus_run_units_total`, `nexus_run_units_per_request`)
- ✅ Metering test suite target (`make test-metering` / `make make-test-metering`)

### Phase 3: Self-Evolution Engine ✅ (6/6 plans coded, wiring closure pass complete)
- ✅ **Plan 01: Core Contracts** — Manifest schema, adapter/generator contracts, artifact bundling, canonical output envelope (106 tests)
- ✅ **Plan 02: Module Generator Gateway** — GitHub Models provider, LLM Gateway with purpose-based routing, schema validation, budget tracking (47 tests)
- ✅ **Plan 03: Sandboxed Validation Loop** — Dual-layer import enforcement, deny-by-default policies, merged validation reports, artifact capture (64 tests)
- ✅ **Plan 04: Self-Correction Pipeline** — Stage-based builder, bounded repair loop (max 10 attempts), failure fingerprinting, install attestation guard (14 tests)
- ✅ **Plan 05: Feature Tests + Scenario Library** — Contract suites, capability-driven test harness, chart validation, 5 curated scenarios (93 tests)
- ✅ **Plan 06: RBAC Lifecycle Management** — Draft lifecycle, validation/promotion with attestation, instant rollback, dev-mode admin API with RBAC

**Wiring closure status (cross-feature verified):**
1. ✅ `build_module`/`repair_module` orchestrator tool registration validated
2. ✅ `repair_module` invokes `gateway.generate(purpose=REPAIR)` in repair path
3. ✅ Dashboard chart artifact routes added for visibility (`/modules/{category}/{platform}/charts`)

### Phase 4: Release-Quality Verification ✅ (4/4 plans complete)
- ✅ **Plan 01: OTC Policy Storage & Reward** — OTC-GRPO reward function, SQLite policy checkpoint storage, trajectory logging with reward separation (37 tests)
- ✅ **Plan 02: Admin API Integration Tests** — Module CRUD, credential ops, config hot-reload, billing endpoints with RBAC enforcement (46 tests)
- ✅ **Plan 03: Unified Verify Command** — `make verify` chains 7 test tiers, latency snapshot (p50/p95/p99), structured pass/fail report (10 tests)
- ✅ **Plan 04: Provider Lock/Unlock** — Base class + 5 provider handlers, connection test API, settings UI lock gating (12 tests)

### Phase 5: Refactoring ✅ (4/4 plans complete)
- ✅ **Plan 01: Module Deduplication** — 5 shared modules (security_policy, static_analysis, identifiers, hashing, validation_types), eliminated 6 areas of code duplication, 40 tests, zero regressions
- ✅ **Plan 02: Agent Soul.md + Auto-Prompt Composition** — 3 soul.md agent identity files (builder, tester, monitor), auto-prompt composition pipeline, Blueprint2Code confidence scorer (threshold 0.6), bounded retry with jitter (max 5 attempts, exponential backoff), 34 tests, 6 commits, 531s execution
- ✅ **Plan 03: Adapter Lock/Unlock + Tool Wiring** — AdapterUnlockBase + 4 subclasses, adapter registry route via Admin API, finance iframe removed, DraftManager/VersionManager registered as 7 orchestrator chat tools, .env manipulation eliminated, 12 tests
- ✅ **Plan 04: Service Dependency Cleanup** — Conditional otel-instrumentation-fastapi import (dashboard starts without it), orchestrator credential proxy eliminated (4 HTTP calls → local _credential_store), SSE pipeline self-probe removed + data deduplication (50% I/O reduction), gRPC service state "idle"→"unknown", ServiceNode UI updated

### Phase 6: UX/UI Visual Expansion ✅ (4/4 plans complete)
- ✅ **Plan 01: Capability Contract + XState Infrastructure** — Pydantic schema, BFF endpoints with ETag, XState v5 root machine, useNexusApp hook, Zustand bridge (25 min, 4 tasks, 10 files)
- ✅ **Plan 02: Dashboard + Adapter Cards** — Dashboard page with XState-backed adapter cards, Framer Motion animations, DataSourceIndicator (30 min, 2 tasks, 4 files)
- ✅ **Plan 03: Finance Dashboard + Chat Actions** — XState financePageMachine with hierarchical states, Recharts LineChart/PieChart, TransactionTable with pagination, ActionCard with Framer Motion, Zustand -> XState refresh (5 min, 2 tasks, 6 files)
- ✅ **Plan 04: Monitoring + Error Taxonomy + Preferences** — XState monitoringPageMachine with parallel regions, React Flow v12 ServiceTopology + PipelineStageFlow, Recharts BarChart with P99 target, error taxonomy (5 types), Framer Motion error components, SQLite user prefs with optimistic concurrency, 6-page navigation (21 min, 3 tasks, 13 files)

### Infrastructure
- ✅ 13-container Docker Compose stack (`docker compose up` → running in <10 min)
- ✅ Unified orchestrator (replaced supervisor-worker mesh, Jan 2026)
- ✅ LIDM routing: Standard (0.5B) / Heavy (14B) tiers
- ✅ Context bridge (HTTP-based orchestrator ↔ dashboard)
- ✅ Sandbox service (gRPC, process-isolated code execution)
- ✅ ChromaDB RAG integration
- ✅ cAdvisor container monitoring
- ✅ Grafana NEXUS Modules dashboard + alert rules

---

## What's In Progress

| Item | Status | Blocker |
|------|--------|---------|
| Phase 4: Release-Quality Verification | **Complete** | None |
| Pipeline UI drag-and-drop | Design phase | — |

---

## Open Risksz

| Risk | Severity | Mitigation |
|------|----------|------------|
| ~~No auth on Admin API or Dashboard~~ | ~~HIGH~~ | ✅ Resolved in Phase 1 — API key auth + RBAC enforced on all endpoints |
| **No approval gates for module install** | HIGH | Malicious adapter code can be enabled without review; mitigated partially by sandbox validation (once A4 complete) |
| ~~No automated tests for Admin API CRUD~~ | ~~MEDIUM~~ | ✅ Resolved in Phase 4 — 46 integration tests covering all CRUD + RBAC |
| **Dashboard SRP violation** | MEDIUM | Single service handles 5+ concerns; harder to scale and test independently |
| **No rate limiting** | MEDIUM | All HTTP endpoints vulnerable to abuse/DoS |
| **SQLite is sufficient for now** | LOW | Module registry, credentials, checkpoints all on SQLite; good enough for local development — scaling migration deferred |

---

## Key Decisions

### Phase 3 Plan 01 (Core Contracts)
- **JSON Schema for manifest validation**: Provides versioned $id for schema evolution tracking, language-agnostic
- **Separate adapter/generator contracts**: Different validation contexts (AST for adapter.py, Pydantic for LLM outputs)
- **Content-addressed artifacts**: SHA-256 bundling before install enables immutable identity and audit trail
- **Canonical output envelope**: Single source of truth (AdapterRunResult) consumed by orchestrator, bridge, UI, metering

### Phase 3 Plan 02 (Module Generator Gateway)
- **GitHub Models inference endpoint (not Copilot IDE)**: Structured code generation with `response_format` json_schema
- **Schema validation rejects, not repairs**: Non-conforming outputs trigger fallback, not silent acceptance
- **Deterministic fallback order**: Same failure condition always selects same next model for predictability
- **Budget enforcement before generation**: Prevents wasted API calls when budget exceeded

### Phase 3 Plan 03 (Sandboxed Validation Loop)
- **Dual-layer import enforcement (static + runtime)**: Static AST check catches obvious violations; runtime hook prevents dynamic bypass attempts
- **Deny-by-default network policy**: Default blocked mode prevents accidental egress; integration mode requires explicit allowlist
- **Merged ValidationReport (static + runtime)**: Single source of truth for LLM repair loop; includes fix hints with context
- **In-process runner for development**: Production uses containers; in-process allows testing policy logic without Docker overhead

### Phase 3 Plan 04 (Self-Correction Pipeline)
- **MAX_REPAIR_ATTEMPTS set to 10**: Configurable constant prevents infinite loops while allowing reasonable repair attempts
- **Failure fingerprints from error types + tests + hints**: Deterministic hash enables thrash detection across repair attempts
- **Terminal failures stop immediately**: Policy/security violations are non-retryable and exit repair loop without wasting attempts
- **JSONL audit logs**: Append-only format supports streaming, replay, and audit analysis
- **Install requires VALIDATED + hash match**: Double verification prevents installing unvalidated or tampered modules

### Phase 3 Plan 06 (RBAC Lifecycle Management)
- **Drafts never directly installable**: Drafts must go through validate_draft() → promote_draft() → install_module() flow to preserve supply-chain integrity
- **Promotion creates new immutable version**: Each promotion generates new bundle_sha256 + attestation, preserving immutability and install guard integrity
- **Rollback is pointer movement only**: Version rollback updates active_versions pointer in SQLite without rebuilding artifacts (instant operation)
- **RBAC enforcement**: Draft create/edit/diff = operator+, validate/promote/rollback = admin+ (approval gate for production changes)
- **Full audit trail**: All dev-mode actions logged with actor identity, timestamps, and artifact hashes for compliance

### Phase 4 Plan 01 (OTC Policy Storage & Reward)
- **Relocated otc_reward.py to shared/billing/**: Phase 2 established shared/billing/ as canonical location for metering infrastructure; maintains subsystem consistency
- **TypedDict for reward return type**: Explicit typing without runtime overhead (vs Pydantic BaseModel with unnecessary validation)
- **Observation/evaluation separation**: trajectory_log captures raw execution data; reward_events stores computed rewards; enables reward function versioning and offline replay
- **Zero-dependency reward function**: Stdlib-only implementation (no numpy/torch) for portability and easier auditing

### Phase 4 Plan 04 (Provider Lock/Unlock)
- **Base class abstraction for provider unlock logic**: Enables dashboard APIs to reuse same validation rules without duplication (vs inline lock logic in routes)
- **Lock only when connection prerequisites missing**: Only lock providers missing required fields (API key + base URL); avoids locking all cloud providers by default
- **Inline connection test results in Settings UI**: Immediate feedback without modal or navigation; keeps UX minimal (vs modal dialog or separate test page)
- **Lightweight connection probes**: Minimal API calls (list models or smallest chat request) for fast fail-fast behavior with 10s timeout

### Phase 5 Plan 02 (Agent Soul.md + Auto-Prompt Composition)
- **Soul.md files as version-controlled artifacts**: Stored in agents/souls/, not config — enables audit trail, reproducible agent behavior, evolution tracking
- **Confidence threshold defaults to 0.6**: Based on Blueprint2Code empirical research showing 0.6+ correlates with successful downstream implementation
- **Max retries defaults to 5**: Balances coverage (>99% of transient errors resolve within 5 attempts) with latency bounds
- **Backoff cap at 30s**: Prevents unbounded delays while allowing sufficient spacing under load per EDMO T4
- **Jitter at 50% of delay**: Optimal distribution per EDMO T4 research, reduces P99 from 2600ms to 1100ms
- **Fail fast on auth errors**: 401/403 are never transient, immediate fallback to next model saves time
- **Repair stage uses compose()**: Scaffold/implement stages still use templates (LLM gateway not wired for those yet)
- **Weighted scoring formula (0.3, 0.3, 0.2, 0.2)**: Completeness and feasibility most critical, edge cases and efficiency secondary

### Phase 6 Plan 01 (Capability Contract + XState Infrastructure)
- **XState v5 setup() API for full TypeScript typing**: Machine context, events, and guards fully typed
- **ETag as SHA-256 of serialized envelope JSON**: Deterministic conditional polling for efficient updates
- **Zustand bridge pattern**: xstateSend registered by useNexusApp, called by chat/other pages for cross-page event dispatch

### Phase 6 Plan 03 (Finance Dashboard + Chat Actions)
- **XState invoked actors (not ad-hoc useEffect)**: testConnection and fetchFinanceData are XState fromPromise actors with proper error handling
- **Framer Motion AnimatePresence mode="wait"**: Exclusive state transitions — one state exits before next enters (no overlapping animations)
- **ResponsiveContainer with initialDimension**: SSR-safe Recharts rendering (prevents hydration mismatches)
- **Zustand bridge for capability refresh**: Tool execution in chat triggers immediate dashboard refresh via XState event dispatch (no 30s poll delay)

### Phase 6 Plan 04 (Monitoring + Error Taxonomy + Preferences)
- **XState parallel regions**: health (30s) + latency (60s) + activeTab run independently — no combinatorial explosion
- **React Flow custom nodes embed shadcn/ui patterns**: ServiceNode uses Card-like styling with Badges and color-mapped status dots
- **Error taxonomy drives XState guards**: isRetryable returns true for TIMEOUT and DEGRADED_PROVIDER, enabling auto-retry
- **SQLite WAL mode for user prefs**: Concurrent reads during optimistic writes, version field for conflict detection
- **Framer Motion layoutId for nav indicator**: Spring animation smoothly transitions between route changes
- **Dynamic imports for heavy libraries**: React Flow (~60KB) and Recharts (~40KB) loaded on-demand per page via next/dynamic

---

## Known Gaps

1. ~~Phase 3 wiring closure~~ — ✅ All gaps closed: DraftManager/VersionManager wired to admin API, usage_store/quota_manager passed to admin server, datetime deprecations fixed. 134 tests passing.
2. **Auth + metering complete, audit/marketplace pending** — auth implemented in Phase 1; metering implemented in Phase 2; audit (Phase 7) and marketplace (Phase 9) remain.
3. **Track C (Co-Evolution)** — Curriculum Agent, Executor Agent, approval gates: 0% complete, planned for Phase 8.
4. **Multi-tenant isolation** — org_id scoping implemented in Phase 1 (registry, credentials, state); full multi-tenant deployment not yet tested at scale.
5. **No E2E tests** for Pipeline UI SSE reconnection.
6. **No centralized logging** — logs are per-container, searched via `docker-compose logs`.

---

## Codebase Metrics (Approximate)

| Metric | Value |
|--------|-------|
| Services | 7 (orchestrator, dashboard, UI, LLM, chroma, sandbox, bridge) |
| Docker containers | 13 (7 services + Prometheus + Grafana + cAdvisor + OTel + Tempo + postgres placeholder) |
| Installed modules | 4 (weather, calendar, gaming, finance) + 1 showroom |
| Unit tests | ~567 (270 base + 106 P3.01 + 47 P3.02 + 64 P3.03 + 14 P3.04 + 21 contract + 8 misc + 37 P4.01 OTC) |
| Integration tests | ~212 (96 base + 46 feature + 26 scenario + 14 self-evolution + 7 install + dev-mode + 12 P4.04 provider-lock) |
| Lines of code (Python) | ~17,000 |
| docs/ files | 11 current + 7 archive |

---

## Progress Snapshot

> Updated 2026-02-17

```
Phase                          Status        Requirements  Done  Remaining
─────────────────────────────  ──────────    ────────────  ────  ─────────
Phase 0: Foundation            complete      —             —     —
Phase 1: Auth Boundary         complete      3             3     0
Phase 2: Run-Unit Metering     complete      4             4     0
Phase 3: Self-Evolution Engine complete      2             2     0
Phase 4: Release-Quality       complete      4             4     0
Phase 5: Refactoring           complete      —             —     —
Phase 6: UX/UI Expansion       complete      4             4     0
Phase 7: Audit Trail           not-started   3             0     3
Phase 8: Co-Evolution          not-started   4             0     4
Phase 9: Enterprise & Market   not-started   12            0     12
─────────────────────────────  ──────────    ────────────  ────  ─────────
TOTAL                                        32            17    19
```

**Phase 3 detail:** 6/6 plans coded (19 artifacts), 134 tests passing (contract + feature + scenario + cross-feature), all wiring complete. DraftManager/VersionManager/UsageStore/QuotaManager wired to admin API. Zero datetime deprecation warnings.

**Phase 4 detail:** 4/4 plans complete. OTC policy storage (5 tables, WAL-mode SQLite) + reward function (otc_tool_reward, compute_composite_reward) + provider lock/unlock (base class + 5 subclasses, connection test endpoint, lock/unlock UI). 49 tests passing (100% pass rate). 8 artifacts created (1,713 lines).

**Phase 6 detail:** 4/4 plans complete. Plan 01 (capability contract): Pydantic schema + BFF endpoints with ETag + XState v5 root machine + useNexusApp hook + Zustand bridge. Plan 02 (dashboard): XState-backed adapter cards + DataSourceIndicator. Plan 03 (finance + chat): XState financePageMachine + Recharts + ActionCard + Zustand refresh. Plan 04 (monitoring + errors + prefs): XState parallel regions + React Flow topology + Recharts latency + error taxonomy + user prefs + navigation. Total: ~81 min, 11 tasks, 36 files.
