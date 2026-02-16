# NEXUS — Roadmap

> **GSD Canonical File** | Updated 2026-02-16

---

## Phase Overview

| # | Phase | Status | Requirements | Target |
|---|-------|--------|--------------|--------|
| 1 | Auth Boundary | **complete** | REQ-001, REQ-002, REQ-003 | Q2 2026 |
| 2 | Run-Unit Metering | **complete** | REQ-006, REQ-007, REQ-008, REQ-009 | Q2 2026 |
| 3 | Self-Evolution Engine | **complete** | REQ-013, REQ-016 | Q2 2026 |
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
- [x] 01-01-PLAN.md — Auth foundation: models, API key store, RBAC permission system
- [x] 01-02-PLAN.md — Middleware + wiring: auth enforcement on Admin API and Dashboard
- [x] 01-03-PLAN.md — Org-scoped data isolation: org_id in AgentState, registry, credentials

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

**Plans:** 3 plans

Plans:
- [x] 02-01-PLAN.md — Billing foundation: RunUnitCalculator, UsageStore, QuotaManager
- [x] 02-02-PLAN.md — Pipeline wiring: instrument _tools_node, quota enforcement in orchestrator
- [x] 02-03-PLAN.md — Billing API endpoints, tests, Makefile target

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

**Plans:** 6 plans (3 waves)

Wave 1 — Contracts + Gateway:
- [x] 03-01-PLAN.md — Builder contracts: manifest schema, generator/adapter contracts, artifact bundles, canonical output envelope (106 tests)
- [x] 03-02-PLAN.md — LLM Gateway: GitHub Models provider, purpose-lane routing (codegen/repair/critic), schema enforcement, fallback chain (47 tests)

Wave 2 — Sandbox + Repair Loop:
- [x] 03-03-PLAN.md — Sandbox policy: network modes, import allowlists (AST + runtime), validator merge, artifact capture (64 tests)
- [x] 03-04-PLAN.md — Self-correction loop: stage pipeline (scaffold/implement/tests/repair), bounded repair (≤10), failure fingerprinting, install attestation guard (14 tests)

Wave 3 — Quality + Dev-Mode:
- [x] 03-05-PLAN.md — Feature tests: contract suites, capability-driven test harness (auth/pagination/rate-limit), chart validation, scenario library (5+ patterns) (93 tests)
- [x] 03-06-PLAN.md — Dev-mode: drafts, diffs, revalidation, promotion, rollback (pointer-based), full audit trail

**Status:** 6/6 plans complete. All wiring gaps closed. 134 tests passing (0 deprecation warnings). DraftManager + VersionManager wired to admin API.

### Deliverables

1. **Builder contracts + artifact system** (REQ-013, REQ-016)
   - Module format fixed: `{manifest.json, adapter.py, test_adapter.py}`
   - Strict generator response contract (no markdown fences, path allowlist, size bounds)
   - Content-addressed immutable artifact bundles (sha256 per file + bundle)
   - Canonical `AdapterRunResult` envelope for orchestrator, bridge, UI, metering

2. **LLM Gateway** (REQ-013)
   - GitHub Models `chat/completions` API as primary inference surface (not Copilot IDE)
   - Purpose-lane routing: codegen, repair, critic — config-driven model selection
   - `response_format` with `json_schema` enforcement; non-conforming outputs rejected
   - Deterministic fallback chain on provider/model outage
   - Integrated as `shared/providers/` module (follows existing provider pattern)

3. **Cloud sandbox build pipeline** (REQ-013)
   - `build_module` tool: NL intent → scaffold → implement → tests → repair → install
   - All execution in sandbox container — user needs only Docker
   - Sandbox policy: deny-by-default network, import allowlist (AST + runtime hook), resource caps
   - Validation produces merged report (static + runtime) with structured fix hints

4. **Bounded self-correction loop** (REQ-013, REQ-016)
   - Max 10 repair attempts with immutable per-attempt artifacts
   - Failure fingerprint dedup: stops early on repeated identical failures
   - Terminal vs retryable failure classification (policy violations stop immediately)
   - Install attestation guard: `VALIDATED` status + `bundle_sha256` match required

5. **Automated test generation + feature suites** (REQ-016)
   - Generic contract tests: registration, output schema, error handling
   - Feature-specific tests driven by manifest capabilities (auth, pagination, rate-limit, charts)
   - Chart artifact validation: structural + semantic integrity tiers
   - Deterministic tests: no real sleeps, mock transport, stable fixtures

6. **Scenario library** (REQ-013)
   - 5+ curated build scenarios: REST API, OAuth2 flow, paginated API, file parser, rate-limited API
   - Each scenario: NL intent, expected adapter shape, test suite, known edge cases
   - Exercised in CI for builder regression testing

7. **Dev-mode safe editing** (REQ-013, REQ-016)
   - Draft → edit → diff → revalidate → promote → install → rollback lifecycle
   - Drafts never installable until re-validated and promoted (same attestation guard)
   - Rollback is pointer movement to prior validated version (no rebuild)
   - Full audit trail: actor identity + hashes for every action

### Files to Create/Modify

- `shared/modules/contracts.py` — generator + adapter contract specs
- `shared/modules/manifest_schema.json` — versioned manifest JSON schema
- `shared/modules/artifacts.py` — content-addressed bundle builder + index
- `shared/modules/output_contract.py` — canonical AdapterRunResult envelope
- `shared/modules/audit.py` — per-attempt audit records
- `shared/modules/drafts.py` — draft lifecycle management
- `shared/modules/versioning.py` — version pointer rollback
- `shared/modules/scenarios/` — curated scenario library (5+ patterns)
- `shared/providers/github_models.py` — GitHub Models provider client
- `shared/providers/llm_gateway.py` — purpose-lane routing + schema enforcement
- `tools/builtin/module_builder.py` — stage pipeline + repair loop (extend existing)
- `tools/builtin/module_validator.py` — merged static + runtime validation (extend existing)
- `tools/builtin/module_installer.py` — attestation guard (extend existing)
- `tools/builtin/feature_test_harness.py` — capability-driven test suite selector
- `tools/builtin/chart_validator.py` — chart artifact validation
- `sandbox_service/policy.py` — network, import, resource policy profiles
- `sandbox_service/runner.py` — structured sandbox execution with artifact capture
- `sandbox_service/sandbox_service.py` — extend SAFE_IMPORTS (modify existing)
- `orchestrator/orchestrator_service.py` — wire gateway + build flow (modify existing)
- `orchestrator/admin_api.py` — dev-mode endpoints (modify existing)

### Done Criteria

- User says "build me a weather tracker" → working adapter installed without touching terminal
- Built module produces a chart visible in dashboard
- Builder self-corrects on first sandbox failure (at least 1 retry cycle working)
- 5+ scenario templates exercised in CI
- Dev-mode: create draft, edit, revalidate, promote, rollback — all auditable
- `make test-self-evolution` runs full Phase 3 regression suite and passes

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
