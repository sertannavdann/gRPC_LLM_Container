# NEXUS — Current State

> **GSD Canonical File** | Auto-generated 2026-02-15 from `docs/**`

---

## Current Phase

**Phase 3 (Self-Evolution Engine)** — in progress (Plans 01-03 complete).

**Current Plan**: 3-04 (Installer with Rollback)
**Progress**: 3/6 plans complete

---

## What's Done

### Track A: Self-Evolving Module Infrastructure
- **A1 ✅** Module manifest schema, dynamic loader (`importlib`), SQLite registry
- **A2 ✅** Fernet credential store with encryption at rest
- **A3 ✅** Agent tool integration (`build_module`, `install_module` tools registered)
- **A4 🚧** LLM-driven module builder — stub implemented, template generation in progress

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

### Phase 3: Self-Evolution Engine 🚧
- ✅ **Plan 01: Core Contracts** — Manifest schema, adapter/generator contracts, artifact bundling, canonical output envelope (106 tests)
- ✅ **Plan 02: Module Generator Gateway** — GitHub Models provider, LLM Gateway with purpose-based routing, schema validation, budget tracking (47 tests)
- ✅ **Plan 03: Sandboxed Validation Loop** — Dual-layer import enforcement, deny-by-default policies, merged validation reports, artifact capture (64 tests)
- 📋 Plan 04: Installer with Rollback
- 📋 Plan 05: Repair Loop
- 📋 Plan 06: End-to-End Integration

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
| Phase 3: Self-Evolution Engine | **Plans 01-02 complete, Plan 03 next** | Gateway ready for builder integration |
| Plan 03: Sandboxed Validation Loop | Not started | Awaiting execution |
| Pipeline UI drag-and-drop | Design phase | — |

---

## Open Risks

| Risk | Severity | Mitigation |
|------|----------|------------|
| ~~No auth on Admin API or Dashboard~~ | ~~HIGH~~ | ✅ Resolved in Phase 1 — API key auth + RBAC enforced on all endpoints |
| **No approval gates for module install** | HIGH | Malicious adapter code can be enabled without review; mitigated partially by sandbox validation (once A4 complete) |
| **No automated tests for Admin API CRUD** | MEDIUM | Regressions from refactoring go undetected; manual curl testing only |
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

---

## Known Gaps

1. **Auth + metering complete, audit/marketplace pending** — auth implemented in Phase 1; metering implemented in Phase 2; audit (Phase 5) and marketplace (Phase 7) remain.
2. **Track C (Co-Evolution)** — Curriculum Agent, Executor Agent, approval gates: 0% complete, planned Q2 2026.
3. **Multi-tenant isolation** — org_id scoping implemented in Phase 1 (registry, credentials, state); full multi-tenant deployment not yet tested at scale.
4. **No E2E tests** for Pipeline UI SSE reconnection.
5. **No centralized logging** — logs are per-container, searched via `docker-compose logs`.

---

## Codebase Metrics (Approximate)

| Metric | Value |
|--------|-------|
| Services | 7 (orchestrator, dashboard, UI, LLM, chroma, sandbox, bridge) |
| Docker containers | 13 (7 services + Prometheus + Grafana + cAdvisor + OTel + Tempo + postgres placeholder) |
| Installed modules | 4 (weather, calendar, gaming, finance) + 1 showroom |
| Unit tests | ~423 (270 + 106 from Plan 01 + 47 from Plan 02) |
| Integration tests | ~96 |
| Lines of code (Python) | ~17,000 |
| docs/ files | 11 current + 7 archive |

---

## Progress Snapshot

> Placeholder for `gsd-tools progress table` output.

```
Phase                          Status        Requirements  Done  Remaining
─────────────────────────────  ──────────    ────────────  ────  ─────────
Phase 0: Foundation            complete      —             —     —
Phase 1: Auth Boundary         complete      3             3     0
Phase 2: Run-Unit Metering     complete      4             4     0
Phase 3: Self-Evolution Engine not-started   2             0     2
Phase 4: Release-Quality       not-started   2             0     2
Phase 5: Audit Trail           not-started   3             0     3
Phase 6: Co-Evolution          not-started   4             0     4
Phase 7: Enterprise & Market   not-started   12            0     12
─────────────────────────────  ──────────    ────────────  ────  ─────────
TOTAL                                        30            7     23
```
