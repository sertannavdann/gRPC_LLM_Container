---
phase: 07-audit-trail
plan: 02
subsystem: audit
tags: [fastapi, decorator, contextvars, sqlite, redaction, rbac]

# Dependency graph
requires:
  - phase: 07-audit-trail
    plan: 01
    provides: "shared/audit package: AuditStore.record()/query(), redact(), ActorContext + AuditContextMiddleware, fail-closed AuditWriteError"
provides:
  - "shared/audit/decorator.py: @audit_action(action, resource_type, resource_id, snapshot, store) — sync+async FastAPI mutation wrapper"
  - "16 @audit_action-decorated Admin API mutation endpoints (routing-config, module lifecycle, credentials, system reload, user prefs, api-keys)"
  - "4 authenticated + decorated Dashboard admin mutations (module-credentials, runtime credentials, disconnect)"
  - "DevModeAuditLog sink dual-write: JSONL append + SQLite AuditStore.record(), fail-closed, cross-referenced by jsonl_event_id"
  - "core/graph.py _tools_node ambient actor_context(channel=\"chat\") for chat-tool mutation attribution"
  - "ModuleAdminTool/ModulePipelineTool direct record() calls for enable/disable/credentials/uninstall/install, fail-closed"
affects: [07-03-audit-query-api, 08-co-evolution-approval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "@audit_action decorator: functools.wraps-preserved signature so FastAPI still resolves path/query/body params through __wrapped__"
    - "Actor resolution chain: ambient contextvar (shared.audit.get_actor()) > Starlette Request scan (request.state.user/org_id) > system/default fallback"
    - "AuditContextMiddleware added before the auth middleware's add_middleware() call so it runs INNER (Starlette: last-added = outermost)"
    - "Snapshot-callable dict field names must avoid shared.audit.redaction.SECRET_KEY_PATTERN substrings (e.g. \"credential\") or the backstop redacts safe metadata"

key-files:
  created:
    - shared/audit/decorator.py
    - tests/unit/test_audit_decorator.py
    - tests/integration/admin/test_audit_capture.py
  modified:
    - shared/audit/__init__.py
    - orchestrator/admin_api.py
    - orchestrator/orchestrator_service.py
    - core/graph.py
    - tools/builtin/module_admin.py
    - tools/builtin/module_pipeline.py
    - shared/modules/audit.py
    - dashboard_service/main.py
    - tests/integration/admin/conftest.py
    - tests/integration/cross_feature/test_audit_completeness.py

key-decisions:
  - "api-key creation/rotation endpoints rely on redact()'s backstop (no explicit snapshot) rather than the decorator's snapshot contract, because snapshot(**bound_args) only sees pre-call arguments and the generated key_id/secret only exist post-call — the decorator's own behavior contract (locked by Task 1 unit tests) doesn't pass the handler result into snapshot()"
  - "Renamed the credential-mutation metadata field from \"credential_keys\" to \"field_names\" (Rule 1 bug fix) — the substring \"credential\" trips shared.audit.redaction.SECRET_KEY_PATTERN, which would otherwise redact the safe list-of-field-names down to a bare \"[REDACTED]\" string"
  - "Bootstrap endpoint (public, unauthenticated) records via a direct _audit_store.record() call instead of @audit_action, since there is no request.state.user for the decorator's actor resolution to find"
  - "Single shared AuditStore constructed once in OrchestratorService.__init__ and reused (not reconstructed) at the second DevModeAuditLog/start_admin_server call site in serve(), avoiding two independent SQLite connections to the same audit_events.db"

requirements-completed: ["REQ-011"]

# Metrics
duration: ~75min (across two work sessions; a stream watchdog interruption after Task 1 paused execution before Task 2/3 resumed from committed state)
completed: 2026-08-14
---

# Phase 7 Plan 2: Audit Decorator + Full Mutation-Path Wiring Summary

**`@audit_action` FastAPI decorator plus wiring into every mutation surface — 16 decorated Admin API endpoints, 4 decorated+authenticated Dashboard endpoints, DevModeAuditLog SQLite dual-write, and direct fail-closed `record()` calls from chat-tool strategies under ambient actor context — so no mutation path in NEXUS can bypass the audit trail (REQ-011).**

## Performance

- **Duration:** ~75 min of active work across two sessions (interrupted by a stream watchdog timeout after Task 1; resumed cleanly from the committed state)
- **Started:** 2026-08-13T00:35:00Z (approx, worktree base commit)
- **Completed:** 2026-08-14
- **Tasks:** 3/3
- **Files modified:** 13 (3 created, 10 modified)

## Accomplishments
- `shared/audit/decorator.py` — `@audit_action(action, resource_type, resource_id=None, snapshot=None, store=None)` wraps sync and async handlers; actor resolution chain (contextvar → Starlette `Request` scan → `"system"/"default"` fallback); `resource_id` string-templates over bound args; snapshot exceptions are tolerated (logged, event still recorded); handler exceptions propagate WITHOUT recording; `AuditWriteError` → `HTTPException(500)` (D-03 fail-closed); store resolved lazily via `get_audit_store()` at call time
- `orchestrator/admin_api.py` — 16 `@audit_action`-decorated mutation endpoints (routing-config CRUD, module enable/disable/reload/uninstall/credentials, system reload, user prefs, API key create/revoke/rotate); `AuditContextMiddleware` added before `APIKeyAuthMiddleware` (Starlette: last-added is outermost, so this ordering makes audit context run *inner*, after auth sets `request.state.user`); `start_admin_server` gained `audit_store=` + `set_audit_store()` wiring; public `/admin/bootstrap` records directly (no request-scoped user to decorate against); draft/version lifecycle endpoints (live block + the pre-existing dead/shadowed block) switched their `DevModeAuditLog` actor argument from `user.org_id` to `user.user_id` per the interface contract; Phase 8's approve/reject endpoints deliberately left undecorated (already covered by the `DevModeAuditLog` sink dual-write — decorating would double-record)
- `dashboard_service/main.py` — `AuditContextMiddleware` wired the same way; the four previously-unauthenticated admin mutations (module-credentials POST/DELETE, `/admin/credentials`, `/admin/disconnect`) now require `Depends(get_current_user)` and are `@audit_action`-decorated with presence-boolean (not value) env-var snapshots
- `shared/modules/audit.py` — `DevModeAuditLog.__init__` gained `sink=` (an `AuditStore`); `log_action()` dual-writes into the sink after the JSONL append with **no try/except** around the sink call — a sink failure propagates to the caller (D-03), while the JSONL side is already durable
- `orchestrator/orchestrator_service.py` — one `AuditStore` constructed in `OrchestratorService.__init__`, registered as the process-wide singleton via `set_audit_store()`, and threaded through both `DevModeAuditLog` instances, `ModuleAdminTool`, `ModulePipelineTool`, and `start_admin_server`
- `core/graph.py` — `_tools_node` wraps its tool-execution loop in `actor_context(ActorContext(actor_id=state.get("user_id") or "chat_agent", org_id=state.get("org_id") or "default", channel="chat"))`, giving every chat-invoked tool call ambient actor identity without threading it through call signatures
- `tools/builtin/module_admin.py` — `EnableStrategy`/`DisableStrategy`/`CredentialStrategy`/`UninstallStrategy` record audit events directly via a shared `_record_mutation()` helper, fail-closed on `AuditWriteError` (`{"status": "error", "error": "audit write failed"}`); draft-lifecycle strategies resolve `actor=` via `get_actor()` instead of the previous hardcoded `"chat_agent"`
- `tools/builtin/module_pipeline.py` — `InstallStrategy` records `module_installed` on success, same fail-closed contract
- Task 3 integration coverage: HTTP mutation capture (actor/org/IP), handler-exception non-recording, store-failure → 500 with unchanged event count, credential redaction (byte-level assertion that the raw secret never lands in the DB file), `DevModeAuditLog` dual-write with `jsonl_event_id` cross-reference and sink-failure propagation, chat-tool actor resolution with and without ambient context, and SQLite-parity assertions extended into `test_audit_completeness.py` for the full draft/version lifecycle

## Task Commits

Each task was committed atomically:

1. **Task 1: `@audit_action` decorator + unit tests** - `674e6bf` (feat) — 15-test unit suite
2. **Task 2: Wire all capture paths (orchestrator, dashboard, tools, graph, dual-write)** - `c0cc303` (feat)
3. **Task 3: Integration tests — capture parity across paths** - `b4ad760` (test) — includes the `field_names` rename bug fix (see Deviations)

**Plan metadata:** (pending — orchestrator commits SUMMARY.md separately after wave merge)

## Files Created/Modified
- `shared/audit/decorator.py` - `@audit_action` decorator (sync + async, actor resolution, snapshot, fail-closed)
- `shared/audit/__init__.py` - exports `audit_action`
- `tests/unit/test_audit_decorator.py` - 15-test unit suite for the decorator
- `orchestrator/admin_api.py` - 16 decorated mutation endpoints, `AuditContextMiddleware` wiring, `audit_store=` on `start_admin_server`, bootstrap direct-record, draft/version `actor=` fix
- `orchestrator/orchestrator_service.py` - single shared `AuditStore` construction + threading
- `core/graph.py` - `_tools_node` ambient `actor_context(channel="chat")`
- `tools/builtin/module_admin.py` - direct fail-closed `record()` calls in mutating strategies + `get_actor()` for draft strategies
- `tools/builtin/module_pipeline.py` - `InstallStrategy` records `module_installed`
- `shared/modules/audit.py` - `DevModeAuditLog` sink dual-write (D-01)
- `dashboard_service/main.py` - `AuditContextMiddleware` + 4 authenticated/decorated admin mutations
- `tests/integration/admin/conftest.py` - `audit_store` fixture, `AuditContextMiddleware` wiring, 3 representative decorated endpoints in the test app
- `tests/integration/admin/test_audit_capture.py` - capture parity integration suite (12 tests)
- `tests/integration/cross_feature/test_audit_completeness.py` - `TestAuditSQLiteParity` extension (3 new tests)

## Decisions Made
- API-key create/rotate endpoints intentionally rely on `redact()`'s automatic backstop rather than an explicit `snapshot=` — the decorator's locked behavior contract only passes *pre-call* bound args to `snapshot()`, and the generated key/`key_id` only exist after the store call, so the handler's own return dict (with the raw key already redacted by the store-layer backstop, since `"api_key"`/`"new_api_key"` both match `SECRET_KEY_PATTERN`) is the only correct source of truth for `after_state` in this case.
- The freshly-merged Phase 8 approve/reject endpoints in `admin_api.py` were left completely untouched (not even the `actor=` fix) per the coordination notes — they already flow through `DevModeAuditLog` → sink, and decorating them would double-record the same mutation.
- Single `AuditStore` instance is constructed once (in `OrchestratorService.__init__`) and reused at the second `DevModeAuditLog`/`start_admin_server` call site in `serve()`, rather than building two separate `AuditStore` objects against the same SQLite file — avoids redundant connection/WAL setup and keeps `set_audit_store()`'s singleton unambiguous.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `credential_keys` field name tripped the redaction backstop, destroying its own safe metadata**
- **Found during:** Task 3 (writing `test_audit_capture.py`'s credential-redaction test)
- **Issue:** `shared.audit.redaction.SECRET_KEY_PATTERN` matches any dict *key* containing the substring `"credential"` (one of its alternatives is the bare word `credential`). The plan's interface notes specified `details={"credential_keys": sorted(creds)}` for credential-mutation events — but that key name itself trips the pattern, so `redact()` collapsed the entire safe list-of-field-names value down to the string `"[REDACTED]"` at the store layer, defeating the purpose of recording *which* credential fields were touched (a truth this plan is required to preserve).
- **Fix:** Renamed the metadata field from `"credential_keys"` to `"field_names"` everywhere it is produced: `orchestrator/admin_api.py` (`_credential_keys_snapshot`), `dashboard_service/main.py` (`_module_credential_keys_snapshot`), `tools/builtin/module_admin.py` (`CredentialStrategy`), and the test app factory in `tests/integration/admin/conftest.py`. Added inline comments at each site explaining why the literal substring `"credential"` must be avoided in this dict key.
- **Files modified:** `orchestrator/admin_api.py`, `dashboard_service/main.py`, `tools/builtin/module_admin.py`, `tests/integration/admin/conftest.py`, `tests/integration/admin/test_audit_capture.py`
- **Verification:** `TestCredentialRedaction::test_credential_mutation_carries_key_names_only` and `TestChatToolActorCapture::test_credential_strategy_never_records_raw_value` both failed before the fix (asserting `{"field_names": [...]}` against an actual value of `"[REDACTED]"`) and pass after it.
- **Committed in:** `b4ad760` (Task 3 commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The fix directly preserves a must-have truth from the plan's frontmatter ("credential events carry key names only") that the interface notes' literal suggested field name would have silently violated. No scope creep — confined to the exact snapshot/details field name across the files already in this plan's `files_modified` list.

## Issues Encountered
- **Environment: `tests/integration/admin/` and the wider `integration/` tree require a live orchestrator gRPC service on port 50054** (a session-scoped `autouse` fixture in `tests/integration/conftest.py`, pre-existing and explicitly documented in `test_approval_gate.py`'s own docstring as intentional — not something this plan should change). Docker itself is available in this environment but the orchestrator container was not running, so `integration/admin/test_audit_capture.py` and the rest of `integration/admin/` report as **skipped**, not failed, in this sandbox (88 skipped, 0 failed — up from 76 skipped pre-plan, with 0 regressions). All 12 new tests in `test_audit_capture.py` were independently verified functionally correct by running them with `--confcutdir=tests/integration/admin` (which excludes the Docker-gated parent conftest while still loading `tests/integration/admin/conftest.py` and `tests/conftest.py`'s sys.path setup) — 12/12 passed under that bypass. `tests/integration/cross_feature/test_audit_completeness.py` is NOT Docker-gated (its local conftest overrides the parent `test_environment` fixture as a no-op) and ran normally: 10/10 passed, including the 3 new SQLite-parity tests.
- `make audit-test` (17 passed) and `make auth-test` (61 passed) both green — no middleware-ordering or RBAC regressions from the `AuditContextMiddleware` insertion.
- Local proto stubs (`*_pb2.py`) were not pre-generated in this worktree, which initially blocked `import orchestrator.admin_api` (unrelated to this plan's changes — `orchestrator/__init__.py` transitively imports `llm_service.llm_pb2`). Ran `make proto-gen` (gitignored output, no repo changes) to unblock local verification; this is a one-time local dev-environment step, not a code change.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- REQ-011 fully delivered: every Admin API mutation, every Dashboard admin mutation, every `DevModeAuditLog`-backed draft/version lifecycle action, and every chat-tool mutation (`ModuleAdminTool`/`ModulePipelineTool`) now feeds the single `AuditStore` sink from 07-01, fail-closed throughout.
- `shared.audit.audit_action` is a stable, independently-tested primitive (Task 1) that Plan 07-03's query API can reference for read-side RBAC parity if needed.
- The `field_names` naming convention (avoiding `SECRET_KEY_PATTERN` substrings in dict *keys*, not just values) is now a documented gotcha inline at every call site — future plans adding new snapshot/details payloads should be aware secret-shaped key *names* (not just values) get swept by the redaction backstop.
- No blockers for 07-03 (audit query API) or Phase 8 (co-evolution approval, which already integrates with the `DevModeAuditLog` sink from this plan's Task 2 wiring).

---
*Phase: 07-audit-trail*
*Completed: 2026-08-14*

## Self-Check: PASSED

All created files verified present on disk (shared/audit/decorator.py,
tests/unit/test_audit_decorator.py, tests/integration/admin/test_audit_capture.py,
this SUMMARY.md). All task commit hashes (674e6bf, c0cc303, b4ad760, 2e84f24)
verified present in `git log`.
