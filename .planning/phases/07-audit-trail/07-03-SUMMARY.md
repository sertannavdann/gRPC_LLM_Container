---
phase: 07-audit-trail
plan: 03
subsystem: audit
tags: [fastapi, rbac, csv-export, hash-chain, grafana, opentelemetry, prometheus]

# Dependency graph
requires:
  - phase: 07-audit-trail
    plan: 01
    provides: "shared/audit package: AuditStore (record/query/count/iter_events/verify_chain), redact(), ActorContext + AuditContextMiddleware"
  - phase: 07-audit-trail
    plan: 02
    provides: "@audit_action decorator + full mutation-path wiring; single shared AuditStore constructed in OrchestratorService.__init__ and registered via set_audit_store()"
provides:
  - "Permission.READ_AUDIT (admin+; OWNER automatic via set(Permission))"
  - "GET /admin/audit-logs — filtered, paginated, org-scoped audit query API"
  - "GET /admin/audit-logs/export — streaming CSV with formula-injection guard"
  - "GET /admin/audit-logs/verify — hash-chain verification endpoint (D-02)"
  - "AuditMetrics (nexus_audit_events_total, nexus_audit_write_failures_total) wired into AuditStore.record() via a lazy, fully-guarded module-level holder"
  - "Grafana 'Audit Trail' row (panel ids 17-20) in nexus-modules.json"
  - "AUDIT_DB_PATH env var on both orchestrator and dashboard containers, resolving to the same host ./data/audit_events.db file"
affects: [08-co-evolution-approval, 09-enterprise-marketplace]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Module-global _audit_store (not get_audit_store()) referenced directly in admin_api.py's three new endpoints, matching the existing decorator/dual-write convention set in 07-02"
    - "Lazy module-level metrics holder in shared/audit/store.py: created on first record() call via _get_audit_metrics(), any construction failure cached as a sentinel so it is never retried per-call; both increment call sites wrap the entire metrics.add() path (including the _get_audit_metrics() call itself) in try/except so a broken telemetry backend can never block or fail the audit write it is measuring"
    - "Owner org-scoping is opt-in, not opt-out: non-OWNER callers are always forced to their own org_id; OWNER sees all orgs unless ?org_id= is explicitly passed"
    - "CSV formula-injection guard: any cell whose rendered text starts with =, +, -, or @ gets a leading apostrophe before being written"

key-files:
  created:
    - tests/integration/admin/test_audit_query_api.py
  modified:
    - shared/auth/rbac.py
    - orchestrator/admin_api.py
    - tests/integration/admin/conftest.py
    - shared/observability/metrics.py
    - shared/audit/store.py
    - tests/unit/test_audit_store.py
    - config/grafana/provisioning/dashboards/json/nexus-modules.json
    - docker-compose.yaml
    - Makefile

key-decisions:
  - "OWNER org-scoping semantics: the plan's interface notes and frontmatter truth ('org-scoped to the caller unless OWNER') left open whether an OWNER omitting ?org_id= sees zero orgs, their own org, or all orgs. Chose 'all orgs' (no org_id filter applied at all) as the only interpretation consistent with 'unless OWNER' meaning OWNER is exempt from scoping by default, with ?org_id= as an opt-in narrowing — verified via test_owner_without_org_param_sees_all_orgs and test_owner_may_scope_to_other_org_via_param."
  - "Endpoints appended at the true end of admin_api.py (after start_admin_server), not interleaved with unrelated endpoint groups — matches the interface note's 'minimizes conflict surface' rationale and keeps route registration order visually distinct as the newest addition."
  - "Metrics guard placed around the entire _get_audit_metrics() call (not just the .add() call) in both _record_metric_success/_record_metric_failure, strengthening the interface note's 'guarded so environments without OTel wiring still work' requirement to also cover a hypothetically broken metrics-factory reference, not just meter creation itself."
  - "CSV export and query share one _audit_query_filters() helper (admin_api.py) / closure (conftest.py test app) rather than duplicating org-scoping logic per endpoint, so the org-scoping semantics decision above only has one implementation to get right."

requirements-completed: ["REQ-012"]

# Metrics
duration: ~25min
completed: 2026-08-14
---

# Phase 7 Plan 3: Audit Query API + Observability Summary

**RBAC-gated audit read surface (filtered query, streaming CSV export with an injection guard, hash-chain verify endpoint) plus OTel metrics, a Grafana "Audit Trail" row, and the docker-compose env vars that make orchestrator and dashboard share one audit DB — closing REQ-012 and D-02's "verification exposed as a check."**

## Performance

- **Duration:** ~25 min
- **Started:** 2026-08-14T01:30:53+03:00 (worktree base commit cfacef5)
- **Completed:** 2026-08-14T01:45:20+03:00
- **Tasks:** 2/2
- **Files modified:** 9 (1 created, 8 modified)

## Accomplishments
- `Permission.READ_AUDIT` added to `shared/auth/rbac.py`, granted to ADMIN; VIEWER/OPERATOR excluded; OWNER automatic (ADMIN's permission set remains a documented subset of OWNER's `set(Permission)`, preserving the existing `test_permission_hierarchy` invariant)
- `GET /admin/audit-logs` — date/actor/action/resource_type/resource_id filters, `limit`/`offset` pagination (limit clamped to `[1, 1000]`), `{"events", "count", "total", "limit", "offset"}` response shape, results ordered `id DESC` (via `AuditStore.query()`); org-scoped to the caller's `org_id` unless the caller is OWNER, in which case `?org_id=` optionally narrows the scope and omitting it queries across all orgs
- `GET /admin/audit-logs/export` — `StreamingResponse` (`text/csv`) iterating `AuditStore.iter_events(batch_size=1000)` in one `io.StringIO` buffer flushed per row, `Content-Disposition: attachment; filename="audit_events_<UTC yyyy-mm-dd>.csv"`, and a formula-injection guard that prefixes any cell starting with `=`, `+`, `-`, or `@` with a literal apostrophe
- `GET /admin/audit-logs/verify` — returns `dataclasses.asdict(AuditStore.verify_chain(start_id=, end_id=))`, exposing D-02's tamper-evidence check as an admin endpoint (first invalid row id + reason on failure)
- All three endpoints read the module-global `_audit_store` set by `start_admin_server` (matching the existing `_config_manager`/`_api_key_store` convention), mirrored into `tests/integration/admin/conftest.py`'s `create_test_admin_app()` against `app.state.audit_store` so the test app stays free of an `orchestrator/` import
- `AuditMetrics` (`nexus_audit_events_total`, `nexus_audit_write_failures_total`) added to `shared/observability/metrics.py` following the `ModuleMetrics`/`create_module_metrics()` factory pattern exactly; wired into `AuditStore.record()` via a lazy, exception-swallowing module-level holder — success increments `audit_events_total` with `{action, resource_type, channel}` (channel resolved from the ambient `ActorContext` set by 07-02's wiring, defaulting to `"system"`), failure increments `audit_write_failures_total` with `{action, resource_type}` immediately before `AuditWriteError` is raised
- Grafana `nexus-modules.json` gained an "Audit Trail" row (panel id 17, `y=40`) with `Audit Events by Action` timeseries (18, `sum by (action) (rate(...))`), `Audit Events (24h)` stat (19), and `Audit Write Failures (24h)` stat with a red `>0` threshold (20) — `grpc_llm_` prefix / `_total` suffix naming matches the existing `nexus_module_*` panels; inserted in-place preserving the file's original compact JSON style (66-line diff, no reformatting churn)
- `docker-compose.yaml`: `AUDIT_DB_PATH=/app/data/audit_events.db` on orchestrator and `AUDIT_DB_PATH=/app/shared_data/audit_events.db` on dashboard — both resolve to the same host `./data/audit_events.db` file via each service's existing volume mount (identical trick to `AUTH_DB_PATH`)
- `Makefile`'s `audit-test` target now runs all four audit test files (`unit/test_audit_store.py`, `unit/test_audit_decorator.py`, `integration/admin/test_audit_capture.py`, `integration/admin/test_audit_query_api.py`)

## Task Commits

Each task was committed atomically (TDD RED → GREEN for Task 1; Task 2 is non-TDD):

1. **Task 1 RED: failing tests for audit query API** - `cc6c7b4` (test) — 31 tests against the not-yet-wired endpoints; strict-RED verified by temporarily stashing the `Permission.READ_AUDIT` scaffolding edit and confirming all 31 fail before restoring it
2. **Task 1 GREEN: READ_AUDIT permission + query/export/verify endpoints** - `359aaa1` (feat) — 31/31 passing
3. **Task 2: Metrics, Grafana row, compose env, Makefile finalization** - `dc18021` (feat)

**Plan metadata:** (pending — orchestrator commits SUMMARY.md separately after wave merge)

## Files Created/Modified
- `shared/auth/rbac.py` - `Permission.READ_AUDIT`, granted to `ADMIN`
- `orchestrator/admin_api.py` - `query_audit_logs`/`export_audit_logs`/`verify_audit_chain` endpoints, `_audit_query_filters()`/`_audit_csv_cell()` helpers, module-level imports (`csv`, `dataclasses`, `io`, `json`, `datetime`/`timezone`, `StreamingResponse`, `Role`)
- `tests/integration/admin/conftest.py` - mirrored the three endpoints in `create_test_admin_app()` against `app.state.audit_store`; `app.state.audit_store = None` default added
- `tests/integration/admin/test_audit_query_api.py` - 31-test suite: RBAC matrix (all 3 endpoints × 4 roles), query filters/pagination/ordering, org scoping (admin forced to own org, owner opt-in/opt-out), CSV header/columns/Content-Disposition/injection guard/org-scoping, verify valid-chain/tampered-chain/`first_invalid_id`/start-end range
- `shared/observability/metrics.py` - `AuditMetrics` dataclass + `create_audit_metrics()`
- `shared/audit/store.py` - lazy `_get_audit_metrics()` holder, `_record_metric_success`/`_record_metric_failure` static helpers wired into `record()`'s success/exception paths, `from .context import get_actor` import for channel attribution
- `tests/unit/test_audit_store.py` - `TestAuditMetrics`: success increment + attrs, ambient-actor channel attribution, failure increment on a read-only-DB write failure, and a guard test proving a raising `_get_audit_metrics()` never blocks `record()`
- `config/grafana/provisioning/dashboards/json/nexus-modules.json` - panels 17-20 (Audit Trail row + 3 panels)
- `docker-compose.yaml` - `AUDIT_DB_PATH` on orchestrator and dashboard env blocks
- `Makefile` - `audit-test` target finalized to all four audit test files

## Decisions Made
- **OWNER org-scoping default is "all orgs," not "no orgs."** The plan's truth ("org-scoped to the caller unless OWNER") and interface notes ("Owner may pass ?org_id=") left the no-param OWNER case ambiguous. Interpreted "unless OWNER" as OWNER being exempt from forced scoping by default — omitting `?org_id=` returns events across every org, and passing it narrows to one org. Locked in by `test_owner_without_org_param_sees_all_orgs` and `test_owner_may_scope_to_other_org_via_param`.
- **New endpoints appended at the literal end of `admin_api.py`**, after `start_admin_server` (the file's actual last function), rather than inserted mid-file near other GET endpoints — matches the interface note's "minimizes conflict surface" instruction literally.
- **Metrics guard wraps the `_get_audit_metrics()` call itself**, not just the resulting counter's `.add()` call, in both `_record_metric_success`/`_record_metric_failure`. The interface note asked for degradation "so environments without OTel wiring still work" (already true by default since `opentelemetry.metrics.get_meter()` returns a no-op meter) — this goes one step further so even a corrupted/monkeypatched metrics accessor can never propagate into a failed or blocked audit write, verified by `test_metrics_failure_does_not_block_write`.
- **Shared `_audit_query_filters()` helper** (duplicated verbatim between `admin_api.py` and the `conftest.py` test-app closure, following the existing pattern of duplicated helpers like `_module_credential_keys_snapshot`) centralizes the org-scoping decision so query and export can't drift apart.

## Deviations from Plan

None - plan executed exactly as written. The OWNER-scoping ambiguity above was resolved using explicit reasoning documented in Decisions Made, not a deviation from any stated behavior — the plan's "Claude's Discretion" section for 07-CONTEXT.md explicitly leaves such wiring specifics open.

## Issues Encountered
- Local verification of `tests/integration/admin/*` requires generated protobuf stubs (`orchestrator/__init__.py` transitively imports `llm_service.llm_pb2`, which isn't checked into the worktree). Ran `make proto-gen` (gitignored output, no repo changes) once at the start of Task 1 to unblock `--confcutdir=tests/integration/admin` bypass runs — a one-time local dev-environment step carried over from 07-02, not a code change.
- `python -m pytest tests/integration/admin/test_billing_endpoints.py tests/integration/admin/test_module_crud.py --confcutdir=tests/integration/admin` shows 6 pre-existing failures (`TestBillingWithUsage` × 3, `TestModuleCRUDEndpoints::test_disable_module_not_found`, `TestModuleWithMockModule` × 2) — confirmed present on the unmodified base commit (`cfacef5`) via a temporary `git stash` of this plan's changes before restoring them. Out of scope per the executor's scope boundary (unrelated files, pre-existing on base); not touched.
- `make audit-test` and the full `tests/integration/admin/` suite both show all audit-related integration tests as `SKIPPED` (not failed) when run without `--confcutdir` bypass, gated by the pre-existing `tests/integration/conftest.py` autouse fixture requiring the orchestrator gRPC service on port 50054 — identical convention documented in 07-02's SUMMARY. All 31 new tests were independently verified passing (not just collected) via the bypass technique.

## User Setup Required
None - no external service configuration required. `AUDIT_DB_PATH` env vars are wired with sensible defaults (`data/audit_events.db` fallback in `AuditStore.__init__`/`get_audit_store()`); the docker-compose values only need `docker compose up` to take effect.

## Next Phase Readiness
- REQ-012 fully delivered: filtered/paginated query, streaming CSV export with an injection guard, hash-chain verification exposed as an endpoint (closing D-02's "verification exposed as a check"), Grafana panel, and RBAC-gated (READ_AUDIT) read access — org-scoped to the caller unless OWNER.
- Phase 7 (Audit Trail) is now complete across all three plans: 07-01 (store primitives), 07-02 (capture wiring), 07-03 (query API + observability). No known blockers for Phase 8 (co-evolution approval), which already depends on the `DevModeAuditLog` sink dual-write from 07-02 and can additionally query approval events through this plan's `/admin/audit-logs` API if needed.
- The `_audit_query_filters()` org-scoping pattern (force non-OWNER to their own org, OWNER opt-in via `?org_id=`) is now the one place this logic lives in `admin_api.py` — future admin read endpoints needing the same org-scoping semantics should reuse or mirror this helper rather than reimplementing the OWNER-exemption check inline.

---
*Phase: 07-audit-trail*
*Completed: 2026-08-14*

## Self-Check: PASSED

All created/modified files verified present on disk (tests/integration/admin/test_audit_query_api.py,
shared/auth/rbac.py, orchestrator/admin_api.py, tests/integration/admin/conftest.py,
shared/observability/metrics.py, shared/audit/store.py, tests/unit/test_audit_store.py,
config/grafana/provisioning/dashboards/json/nexus-modules.json, docker-compose.yaml, Makefile,
this SUMMARY.md). All task commit hashes (cc6c7b4, 359aaa1, dc18021) verified present in `git log`.
