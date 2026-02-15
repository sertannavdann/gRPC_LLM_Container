# NEXUS — Roadmap

> **GSD Canonical File** | Auto-generated 2026-02-15 from `docs/**`

---

## Phase Overview

| # | Phase | Status | Requirements | Target |
|---|-------|--------|--------------|--------|
| 1 | Auth Boundary | planned | REQ-001, REQ-002, REQ-003 | Q2 2026 |
| 2 | Run-Unit Metering | not-started | REQ-006, REQ-007, REQ-008, REQ-009 | Q2 2026 |
| 3 | **Self-Evolution Engine** | not-started | REQ-013, REQ-016 | Q2–Q3 2026 |
| 4 | Release-Quality Verification | not-started | REQ-019, REQ-028 | Q3 2026 |
| 5 | Audit Trail | not-started | REQ-010, REQ-011, REQ-012 | Q3 2026 |
| 6 | Co-Evolution & Approval | not-started | REQ-014, REQ-017, REQ-018, REQ-020 | Q3–Q4 2026 |
| 7 | Enterprise & Marketplace | not-started | REQ-004, REQ-005, REQ-015, REQ-021–REQ-030 | Q4 2026+ |

---

## Phase 1: Auth Boundary (Admin/Bridge)

**Milestone**: "Commercial Hardening — Authentication"

**Goal**: Minimal RBAC matrix for config + module CRUD. Blocks all paid-tier enforcement.

**Plans:** 3 plans

Plans:
- [ ] 01-01-PLAN.md — Auth foundation: models, API key store, RBAC permission system
- [ ] 01-02-PLAN.md — Middleware + wiring: auth enforcement on Admin API and Dashboard
- [ ] 01-03-PLAN.md — Org-scoped data isolation: org_id in AgentState, registry, credentials

### Deliverables

1. **API key authentication** (REQ-001)
   - `shared/auth/api_keys.py` — generation, SHA-256 hashing, validation
   - SQLite table `api_keys` (key_hash, org_id, role, created_at, last_used, rate_limit)
   - FastAPI middleware in `shared/auth/middleware.py`
   - Wired into `orchestrator/admin_api.py` and `dashboard_service/main.py`

2. **RBAC enforcement** (REQ-002)
   - `shared/auth/rbac.py` — Role enum (viewer, operator, admin, owner), permission matrix
   - Permission checks on all Admin API mutation endpoints
   - `shared/auth/models.py` — Organization, User, Role Pydantic models
   - SQLite tables: `organizations`, `users`, `user_roles`

3. **Org-scoped data isolation** (REQ-003)
   - `org_id` field added to `AgentState` in `core/state.py`
   - Module registry, credential store, routing config queries filtered by `org_id`

### Files to Create/Modify

- `shared/auth/` (new package: `__init__.py`, `api_keys.py`, `rbac.py`, `middleware.py`, `models.py`)
- `orchestrator/admin_api.py` — add auth middleware
- `dashboard_service/main.py` — add auth middleware
- `core/state.py` — extend with `org_id`
- `shared/modules/registry.py` — org-scoped queries
- `shared/modules/credentials.py` — org-scoped isolation

### Done Criteria

- Unauthenticated requests to Admin API return 401
- Viewer role cannot enable/disable modules
- Two orgs see isolated module registries

---

## Phase 2: Run-Unit Metering Primitive

**Milestone**: "Commercial Hardening — Metering"

**Goal**: Per tool/model/thread usage metering exported to Prometheus and persisted.

### Deliverables

1. **Run-unit calculator** (REQ-006)
   - `shared/billing/run_units.py` — formula: `max(CPU_s, GPU_s) × tier_multiplier + tool_call_overhead`
   - Hooked into `_tools_node` in `core/graph.py`
   - Tier multipliers: Standard=1.0×, Heavy=1.5×, Ultra=3.0×; tool=0.1, sandbox=0.2 per call

2. **Usage storage and quota enforcement** (REQ-007)
   - `shared/billing/usage_store.py` — SQLite `usage_records` table
   - `shared/billing/quota_manager.py` — tier limits; returns gRPC `RESOURCE_EXHAUSTED` on breach

3. **Billing API** (REQ-008)
   - `GET /admin/billing/usage` — current period by org
   - `GET /admin/billing/usage/history` — historical with date range
   - `GET /admin/billing/quota` — remaining quota

4. **Prometheus counters** (REQ-009)
   - `nexus_run_units_total{org,tier}` counter added to metrics export

### Files to Create/Modify

- `shared/billing/` (new package: `__init__.py`, `run_units.py`, `usage_store.py`, `quota_manager.py`)
- `core/graph.py` — instrument `_tools_node`
- `orchestrator/admin_api.py` — billing endpoints
- `orchestrator/orchestrator_service.py` — quota check before processing

### Done Criteria

- Each request records run units in SQLite
- Prometheus shows `nexus_run_units_total` counter
- Free-tier org blocked after 100 runs/month

---

## Phase 3: Self-Evolution Engine

**Milestone**: "NEXUS Core Differentiator — Cloud Sandbox Module Builder"

**Goal**: The defining feature of NEXUS — users describe what they want in natural language, and the system builds, tests, and deploys a production module **entirely in the cloud sandbox**, with zero local dev environment setup (no conda, pip, venv on the user's machine). Built modules can produce data visualizations (graphs/charts) and pass structured data to the LLM for reference.

### Deliverables

1. **Cloud sandbox build pipeline** (REQ-013)
   - `build_module` tool generates adapter code from NL spec via templates
   - All code generation, dependency resolution, and testing happens inside the sandbox container — user needs only Docker
   - Sandbox validation with self-correction loop (structured fix hints, up to 10 retries)
   - Covers diverse API patterns: REST, OAuth2, paginated, rate-limited, CSV/file-based

2. **Data visualization in modules** (REQ-013)
   - Built modules can produce chart/graph outputs (matplotlib, plotly, or similar rendered server-side)
   - Visualization artifacts passed to LLM as structured context for richer answers
   - Dashboard integration: module outputs rendered in Pipeline UI

3. **Automated test generation** (REQ-016)
   - Builder generates `test_adapter.py` alongside `adapter.py`
   - Tests run in sandbox before approval; >80% coverage target on generated adapters
   - Scenario capture: record API interaction patterns for regression testing

4. **Scenario library** (REQ-013)
   - Curated set of build scenarios: simple REST API, OAuth2 flow, paginated results, file parsing, webhook listener
   - Each scenario has expected adapter shape, test suite, and known edge cases
   - Used for regression testing the builder itself

### Files to Create/Modify

- `tools/builtin/module_builder.py` — full implementation (currently stub)
- `tools/builtin/module_validator.py` — sandbox validation loop
- `shared/modules/templates/` — adapter + test templates per scenario
- `sandbox_service/sandbox_service.py` — extend SAFE_IMPORTS for module build deps
- `orchestrator/orchestrator_service.py` — wire build intent → builder → validator → installer

### Done Criteria

- User says "build me a weather tracker" → working adapter installed without touching terminal
- Built module produces a chart visible in dashboard
- Builder self-corrects on first sandbox failure (at least 1 retry cycle working)
- 5+ scenario templates exercised in CI

---

## Phase 4: Release-Quality Verification

**Milestone**: "Release Confidence Gate"

**Goal**: Single command that runs integration + showroom and records a perf/latency snapshot.

### Deliverables

1. **Admin API integration tests** (REQ-019)
   - `tests/integration/test_admin_api.py` — module CRUD, credential ops, config hot-reload
   - Added to CI/CD pipeline

2. **Unified verification command** (REQ-028)
   - `make verify` runs: unit tests → integration tests → showroom demo → latency snapshot (p50/p95/p99)
   - Outputs structured pass/fail report; non-zero exit on failure

### Done Criteria

- `make verify` exits 0 on healthy system, non-zero on failure
- Latency snapshot persisted as JSON artifact
- Admin API tests cover all CRUD operations

---

## Phase 5: Audit Trail

**Milestone**: "Enterprise Foundation — Audit"

**Goal**: Immutable audit log for all Admin API mutations.

### Deliverables

1. **Audit log storage** (REQ-010)
   - Append-only SQLite `audit_events` table
   - Fields: id, timestamp, org_id, actor_id, action, resource_type, resource_id, before_state, after_state, ip_address

2. **Audit decorator** (REQ-011)
   - `@audit_action(action, resource_type)` for Admin API endpoints
   - Auto-captures before/after state

3. **Audit query API** (REQ-012)
   - `GET /admin/audit-logs` — filter by date, actor, action, resource
   - `GET /admin/audit-logs/export` — CSV export
   - Grafana audit panel in NEXUS dashboard

### Done Criteria

- Every module enable/disable/config change generates an audit record
- Audit log is append-only (no UPDATE/DELETE)
- CSV export works for compliance review

---

## Phase 6: Co-Evolution & Approval

**Milestone**: "Self-Evolving Agent — Safety Gates"

### Deliverables

1. **Module approval gates UI** (REQ-014) — review code, credentials, sandbox results before install
2. **Tiered trace retention** (REQ-017) — per-org retention policies; background cleanup worker
3. **Pipeline SSE E2E tests** (REQ-018) — Playwright tests for reconnection logic
4. **Rate limiting** (REQ-020) — token bucket with 429 + Retry-After on all HTTP endpoints

### Done Criteria

- No module installed without explicit user approval
- Traces auto-purge per retention policy

---

## Phase 7: Enterprise & Marketplace (Future — Ideation Only)

**Milestone**: "Enterprise Scale + Revenue"

> **Note**: This phase is documented for strategic planning. All current development is open-source first.

### Deliverables

- SSO: OAuth2/OIDC + SAML/SCIM (REQ-004, REQ-005)
- Module versioning and rollback (REQ-015)
- Dashboard SRP refactor (REQ-021)
- Finance categorizer OCP fix (REQ-022)
- Centralized credential validation (REQ-023)
- API versioning (REQ-024)
- Marketplace publishing + browse/install (REQ-025, REQ-026)
- Take-rate tracking (REQ-027)
- Adapter caching (REQ-029)
- Centralized logging (REQ-030)

### Done Criteria

- Enterprise org can SSO via Okta/Azure AD
- Marketplace has ≥10 community modules
- All APIs versioned with `/v1/` prefix
