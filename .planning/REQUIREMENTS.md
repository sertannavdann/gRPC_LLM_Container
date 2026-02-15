# NEXUS — Requirements

> **GSD Canonical File** | Auto-generated 2026-02-15 from `docs/**`

---

## Requirements Catalog

### Auth & Access Control

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-001 | API key authentication for Admin API and Dashboard API | P0 | SHA-256 hashed keys in SQLite; middleware rejects unauthenticated requests with 401; key rotation without downtime | docs/archive/PLAN.md §1.1, docs/SECURITY.md |
| REQ-002 | Role-Based Access Control (RBAC) with viewer/operator/admin/owner roles | P0 | Permission matrix enforced: module mgmt → admin+, config changes → admin+, credential ops → owner, read-only → viewer+; roles stored in SQLite | docs/archive/PLAN.md §1.2 |
| REQ-003 | Organization / tenant model with org_id scoping | P1 | Module registry, credential store, and routing config queries scoped by org_id; org_id propagated in AgentState | docs/archive/PLAN.md §1.3 |
| REQ-004 | OAuth2/OIDC SSO (Google, GitHub, Microsoft) | P2 | JWT token issuance; refresh token rotation; session management | docs/archive/PLAN.md §6.1, docs/SECURITY.md |
| REQ-005 | SAML/SCIM support for enterprise identity | P2 | SAML SP metadata; SCIM user provisioning endpoint; directory sync | docs/archive/PLAN.md §6.2 |

### Metering & Billing

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-006 | Run-unit metering primitive | P0 | `Run Unit = max(CPU_s, GPU_s) × tier_multiplier + tool_call_overhead`; per-request compute tracked in `_tools_node` | docs/MONETIZATION_STRATEGY.md §2.2, docs/archive/PLAN.md §2.1 |
| REQ-007 | Usage storage and quota enforcement | P0 | SQLite `usage_records` table; Free: 100 runs/mo, Team: 5000; gRPC RESOURCE_EXHAUSTED on quota breach | docs/archive/PLAN.md §2.2 |
| REQ-008 | Billing/usage API endpoints | P1 | `GET /admin/billing/usage`, `/usage/history`, `/quota`; JSON responses with date-range filtering | docs/archive/PLAN.md §2.3 |
| REQ-009 | Prometheus export of run-unit counters | P1 | `nexus_run_units_total{org,tier}` counter scraped by existing Prometheus job | docs/MONETIZATION_STRATEGY.md |

### Audit & Compliance

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-010 | Immutable audit log for all mutations | P1 | Append-only SQLite table `audit_events`; fields: timestamp, org_id, actor_id, action, resource, before/after JSON | docs/archive/PLAN.md §3.1 |
| REQ-011 | Audit middleware decorator for Admin API | P1 | `@audit_action()` auto-captures before/after state on config, module, and credential mutations | docs/archive/PLAN.md §3.2 |
| REQ-012 | Audit query and CSV export API | P2 | `GET /admin/audit-logs` with date/actor/action filters; `GET /admin/audit-logs/export` returns CSV | docs/archive/PLAN.md §3.3 |

### Module System — Self-Evolution

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-013 | LLM-driven module builder — Cloud Sandbox Engine (Track A4) | P0 | `build_module` tool generates adapter code from NL spec via cloud sandbox — **no local dev environment required** (no conda/pip/venv on user machine); modules can produce data visualizations (graphs/charts) and pass structured data to LLM for reference; template-based scaffolding; sandbox validation with self-correction (up to 10 retries); covers diverse API patterns (REST, OAuth, paginated, rate-limited) | docs/ROADMAP.md, docs/ARCHITECTURE.md, docs/archive/next-phase.md |
| REQ-014 | Module approval gates (Track C3) | P1 | UI review of generated code + required credentials + sandbox test results; approve/reject with feedback loop | docs/ROADMAP.md, docs/KNOWN-ISSUES.md §2 |
| REQ-015 | Module versioning and rollback | P2 | Multiple versions in registry; `POST /admin/modules/{cat}/{plat}/rollback?version={v}`; directory-based `versions/v1/` | docs/KNOWN-ISSUES.md §7 |
| REQ-016 | Automated test generation for built modules | P1 | Builder generates `test_adapter.py` alongside `adapter.py`; tests run in sandbox before approval | docs/ROADMAP.md |

### Observability & Reliability

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-017 | Tiered trace retention (Free 7d / Team 90d / Enterprise unlimited) | P1 | Prometheus retention flags per org; background cleanup worker prunes expired data daily | docs/archive/PLAN.md §4 |
| REQ-018 | E2E tests for Pipeline SSE reconnection | P1 | Playwright tests verify: initial connect, reconnect after dashboard restart, error handling on SSE failure | docs/KNOWN-ISSUES.md §6 |
| REQ-019 | Admin API CRUD integration tests | P0 | `tests/integration/test_admin_api.py` covers enable/disable/reload/uninstall, credential store/retrieve, config hot-reload | docs/KNOWN-ISSUES.md §3 |
| REQ-020 | Rate limiting on all HTTP endpoints | P1 | Redis-backed or in-memory token bucket; configurable per-endpoint; returns 429 with Retry-After header | docs/KNOWN-ISSUES.md §9, docs/SECURITY.md |

### Architecture & Refactoring

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-021 | Dashboard service SRP refactor | P2 | Split into: Context service (aggregation), Adapter service (registry), Finance service (bank), Stream service (SSE) | docs/KNOWN-ISSUES.md §4 |
| REQ-022 | Finance categorizer config-driven (OCP fix) | P2 | Category patterns in JSON/DB config instead of hardcoded regex; extensible without code changes | docs/KNOWN-ISSUES.md §5 |
| REQ-023 | Centralized credential validation | P2 | Single `CredentialStore.validate()` method replaces scattered validation in adapter, dashboard, and admin API | docs/KNOWN-ISSUES.md §8 |
| REQ-024 | API versioning scheme | P2 | URL-based: `/v1/admin/...`; breaking changes require new version prefix | docs/KNOWN-ISSUES.md §10 |

### Marketplace

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-025 | Module publishing API | P2 | Manifest extended with creator_id, price, license, downloads, rating; submission + validation gates | docs/archive/PLAN.md §5.1 |
| REQ-026 | Marketplace browse/install endpoints | P2 | `GET /marketplace/modules` with search/filter/pagination; `POST /marketplace/modules/{id}/install` | docs/archive/PLAN.md §5.2 |
| REQ-027 | Take-rate revenue tracking | P3 | 85/15 creator/platform split; per-module revenue tracked in registry | docs/MONETIZATION_STRATEGY.md §4 |

### Release Quality

| ID | Requirement | Priority | Acceptance Criteria | Source |
|---|---|---|---|---|
| REQ-028 | Single-command integration + showroom + perf snapshot | P0 | `make verify` (or equivalent) runs integration tests, showroom tests, records latency p50/p95/p99, and outputs pass/fail summary | USER_TESTING_GUIDE.md, docs/OPERATIONS.md |
| REQ-029 | Adapter result caching (TTL-based) | P2 | Redis or in-memory cache with configurable TTL per adapter; reduces external API calls and latency | docs/KNOWN-ISSUES.md §11 |
| REQ-030 | Centralized logging (ELK or equivalent) | P3 | Structured JSON logs from all services → central store; searchable via Kibana or Grafana Loki | docs/KNOWN-ISSUES.md §12 |

---

## Traceability

> Maps each requirement to its roadmap phase. Updated after ROADMAP.md generation.

| REQ ID | Phase |
|--------|-------|
| REQ-001 | Phase 1 — Auth Boundary |
| REQ-002 | Phase 1 — Auth Boundary |
| REQ-003 | Phase 1 — Auth Boundary |
| REQ-006 | Phase 2 — Run-Unit Metering |
| REQ-007 | Phase 2 — Run-Unit Metering |
| REQ-008 | Phase 2 — Run-Unit Metering |
| REQ-009 | Phase 2 — Run-Unit Metering |
| REQ-013 | Phase 3 — Self-Evolution Engine |
| REQ-016 | Phase 3 — Self-Evolution Engine |
| REQ-019 | Phase 4 — Release-Quality Verification |
| REQ-028 | Phase 4 — Release-Quality Verification |
| REQ-010 | Phase 5 — Audit Trail |
| REQ-011 | Phase 5 — Audit Trail |
| REQ-012 | Phase 5 — Audit Trail |
| REQ-014 | Phase 6 — Co-Evolution & Approval |
| REQ-017 | Phase 6 — Co-Evolution & Approval |
| REQ-018 | Phase 6 — Co-Evolution & Approval |
| REQ-020 | Phase 6 — Co-Evolution & Approval |
| REQ-004 | Phase 7 — Enterprise & Marketplace |
| REQ-005 | Phase 7 — Enterprise & Marketplace |
| REQ-015 | Phase 7 — Enterprise & Marketplace |
| REQ-021 | Phase 7 — Enterprise & Marketplace |
| REQ-022 | Phase 7 — Enterprise & Marketplace |
| REQ-023 | Phase 7 — Enterprise & Marketplace |
| REQ-024 | Phase 7 — Enterprise & Marketplace |
| REQ-025 | Phase 7 — Enterprise & Marketplace |
| REQ-026 | Phase 7 — Enterprise & Marketplace |
| REQ-027 | Phase 7 — Enterprise & Marketplace |
| REQ-029 | Phase 7 — Enterprise & Marketplace |
| REQ-030 | Phase 7 — Enterprise & Marketplace |
