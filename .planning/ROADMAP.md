# NEXUS — Roadmap

> **GSD Canonical File** | Updated 2026-02-16

---

## Phase Overview

| # | Phase | Status | Requirements | Target |
|---|-------|--------|--------------|--------|
| 1 | Auth Boundary | **complete** | REQ-001, REQ-002, REQ-003 | Q2 2026 |
| 2 | Run-Unit Metering | **complete** | REQ-006, REQ-007, REQ-008, REQ-009 | Q2 2026 |
| 3 | Self-Evolution Engine | **complete** | REQ-013, REQ-016 | Q2 2026 |
| 4 | Release-Quality Verification | **complete** | REQ-019, REQ-028 | Q3 2026 |
| 5 | Refactoring | not-started | — | Q3 2026 |
| 6 | UX/UI Visual Expansion | not-started | REQ-031, REQ-032 | Q3 2026 |
| 7 | Audit Trail | not-started | REQ-010, REQ-011, REQ-012 | Q3 2026 |
| 8 | Co-Evolution & Approval | not-started | REQ-014, REQ-017, REQ-018, REQ-020 | Q3–Q4 2026 |
| 9 | Enterprise & Marketplace | not-started | REQ-004, REQ-005, REQ-015, REQ-021–REQ-030 | Q4 2026+ |

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

**Goal**: Single command that runs integration + showroom and records a perf/latency snapshot. Additionally, bridge Phase 2 run-unit metering to the OTC (Optimal Tool Calls) reward signal for tool-call efficiency tracking.

**Plans:** 4 plans (2 waves)

Wave 1 - OTC Policy Store + Admin API Tests + Provider Lock UX (parallel):
- [x] 04-01-PLAN.md - OTC policy store + reward function: relocate otc_reward.py to shared/billing/, create OTC policy SQLite store, unit tests
- [x] 04-02-PLAN.md - Admin API integration tests: module CRUD, credential ops, config hot-reload, billing endpoints (REQ-019)
- [x] 04-04-PLAN.md - Settings provider lock/unlock architecture: base class + subclasses, API-driven unlock test output, UI gating + integration tests

Wave 2 - Unified Verification:
- [x] 04-03-PLAN.md - Unified verify command + latency snapshot: make verify, p50/p95/p99 recording, structured report (REQ-028)

### Deliverables

1. **OTC Policy Storage + Reward Function**
   - `shared/billing/otc_reward.py` - OTC-GRPO reward bridging Phase 2 run-unit metering to tool-call optimization
   - `shared/billing/otc_policy_store.py` - SQLite store for intent_classes, module_sets, policy_checkpoints, trajectory_log, reward_events
   - Unit tests for reward math and store CRUD

2. **Admin API integration tests** (REQ-019)
   - `tests/integration/admin/` - module CRUD, credential ops, config hot-reload, billing endpoints
   - FastAPI TestClient (in-process, no Docker required)
   - RBAC enforcement verified for viewer/operator/admin roles

3. **Unified verification command** (REQ-028)
   - `make verify` runs: unit -> contract -> integration -> admin API -> feature -> showroom -> latency snapshot (p50/p95/p99)
   - Outputs structured pass/fail report; non-zero exit on failure
   - `--skip-showroom` flag for CI without Docker

### Files to Create/Modify

- `shared/billing/otc_reward.py` - OTC reward function (relocated from root)
- `shared/billing/otc_policy_store.py` - OTC policy checkpoint + trajectory SQLite store
- `shared/billing/latency_snapshot.py` - percentile calculator + JSON snapshot writer
- `tests/unit/test_otc_reward.py` - reward function unit tests
- `tests/unit/test_otc_policy_store.py` - policy store unit tests
- `tests/unit/test_latency_snapshot.py` - latency snapshot unit tests
- `tests/integration/admin/` - Admin API integration test suite
- `scripts/verify.sh` - unified verification pipeline script
- `Makefile` - add verify target

### Done Criteria

- `make verify` exits 0 on healthy system, non-zero on failure
- Latency snapshot persisted as JSON artifact (data/verify_snapshot.json)
- Admin API tests cover all CRUD operations with RBAC
- OTC reward function computes correct r_tool peaking at m==n
- OTC policy store persists all 5 tables in WAL-mode SQLite

---

## Phase 5: Refactoring

**Milestone**: "Clean Codebase — Eliminate Tech Debt Before UI Work"

**Goal**: Consolidate 6 areas of code redundancy, wire soul.md agent identities into the build pipeline, unify adapter lock/unlock with the provider pattern, and register DraftManager/VersionManager as orchestrator chat tools.

**Plans:** 3 plans (2 waves)

Wave 1 — Code Dedup + Agent Wiring (parallel):
- [ ] 05-01-PLAN.md — Code deduplication & dead code removal: FORBIDDEN_IMPORTS, AST import checker, module_id parsing, SHA-256 hashing, validation report shape, dead code
- [ ] 05-02-PLAN.md — Soul.md agent identities + auto-prompt composition: builder/tester/monitor soul.md files, compose() function, Blueprint2Code confidence gate, bounded retry with jitter

Wave 2 — Adapter Unification + Tool Wiring:
- [ ] 05-03-PLAN.md — Adapter lock/unlock unification + tool wiring: AdapterUnlockBase, adapter registry route, finance iframe removal, DraftManager/VersionManager chat tools, .env removal

### Deliverables

1. **Code deduplication** — 6 redundancy areas consolidated into 5 shared modules
2. **Soul.md agent identities** — Builder, Tester, Monitor agents wired into build pipeline with auto-prompt composition
3. **Bounded retry with jitter** — LLM Gateway transient failure resilience (EDMO doc T4)
4. **Adapter lock/unlock** — Provider pattern extended to adapters, Admin API-driven
5. **Finance backend consolidation** — Iframe removed, single API proxy path
6. **Orchestrator tool wiring** — DraftManager + VersionManager as chat tools with RBAC

### Done Criteria

- `grep -rn "FORBIDDEN_IMPORTS\\s*=" --include="*.py" | wc -l` returns exactly 1
- `ls agents/souls/*.soul.md | wc -l` returns 3
- `grep -rn "readFileSync.*env" ui_service/ | wc -l` returns 0
- `grep -rn "iframe" ui_service/src/app/finance/ | wc -l` returns 0
- `make test-self-evolution` passes with zero regressions

---

## Phase 6: UX/UI Visual Expansion

**Milestone**: "Capability-Driven UI — Sync UI with Backend Truth"

**Goal**: Build a designed UX/UI that renders entirely from backend capability contracts. Dashboard shows adapter connectivity. Finance is a native page. Chat triggers adapter actions. Monitoring shows P99 observability. Error states are visible, not silent.

**Plans:** 4 plans (3 waves)

Wave 1 — Backend Capability Contract (Cursor only):
- [ ] 06-01-PLAN.md — Capability schema + BFF endpoints: Pydantic CapabilityEnvelope, GET /capabilities with ETag, GET /feature-health, GET /config/version, contract tests + TypeScript docs

Wave 2 — Capability-Driven Pages (v0 → Cursor, parallel):
- [ ] 06-02-PLAN.md — Dashboard + adapter connectivity: useCapabilities hook with ETag polling, adminClient extension, dashboard adapter cards with connect/disconnect flow
- [ ] 06-03-PLAN.md — Finance page native rewrite + chat bidirectional actions: transaction table, spending charts, lock/unlock gating, chat action cards, dashboard refresh on tool calls

Wave 3 — Monitoring + Polish:
- [ ] 06-04-PLAN.md — Monitoring + P99 observability + user prefs + QA: P99/P95/P50 latency, error taxonomy, error state components, user preferences, navigation update

### Deliverables

1. **Backend capability contract** (REQ-031) — CapabilityEnvelope Pydantic model, three BFF endpoints with ETag
2. **Capability-driven UI pages** (REQ-032) — Dashboard, Finance, Monitoring, Chat actions
3. **UI infrastructure** — useCapabilities, error taxonomy, error state components, useUserPrefs
4. **Per-user preference persistence** — SQLite + optimistic concurrency

### Tool Usage (v0 Premium + Cursor Pro)

| Tool | Role | Cost |
|------|------|------|
| v0 Premium | Visual shell generation | $20/mo |
| Cursor Pro | Repo-aware multi-file wiring | $20/mo |

### Done Criteria

- Every page renders from capability contract data — no hardcoded assumptions
- Error states visible: 401 → degraded banner, invalid JSON → warning, timeout → skeleton
- User preferences persist across page refreshes
- P99 latency < 500ms for all active service endpoints
- `make verify` passes with zero regressions

---

## Phase 7: Audit Trail

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

## Phase 8: Co-Evolution & Approval

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

## Phase 9: Enterprise & Marketplace (Future — Ideation Only)

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
