---
phase: 07-audit-trail
plan: 01
subsystem: audit
tags: [sqlite, hash-chain, redaction, contextvars, wal, tamper-evident]

# Dependency graph
requires:
  - phase: 01-auth-boundary
    provides: "shared/auth/middleware.py request.state.user/org_id contract, APIKeyStore pattern"
  - phase: 02-run-unit-metering
    provides: "shared/billing/usage_store.py SQLite store pattern to mirror (WAL, connection-per-call)"
provides:
  - "shared/audit package: AuditStore (record/query/count/iter_events/verify_chain), redact(), ActorContext + AuditContextMiddleware"
  - "Append-only, hash-chained audit_events SQLite table with tamper detection"
  - "Unconditional store-layer secret redaction (D-04)"
  - "Fail-closed write semantics (AuditWriteError, D-03)"
  - "make audit-test target"
affects: [07-02-audit-decorator, 07-03-audit-query-api, 08-co-evolution-approval]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Append-only SQLite via BEFORE UPDATE/DELETE triggers RAISE(ABORT)"
    - "SHA-256 hash chain (prev_hash/row_hash) from genesis constant for tamper evidence"
    - "BEGIN IMMEDIATE explicit transaction for serialized id assignment under concurrent writers"
    - "contextvar-backed ambient actor identity (ActorContext) for capture without signature threading"
    - "Unconditional redaction at store layer (callers cannot opt out)"

key-files:
  created:
    - shared/audit/__init__.py
    - shared/audit/store.py
    - shared/audit/redaction.py
    - shared/audit/context.py
    - tests/unit/test_audit_store.py
  modified:
    - Makefile

key-decisions:
  - "Hash payload canonicalization uses json.dumps(sort_keys=True, separators=(',',':')) per interfaces contract, over the pre-redaction-applied dict (not the JSON-serialized TEXT column) so verify_chain() can recompute by round-tripping stored JSON back to python objects"
  - "record() drives its own dedicated sqlite3 connection with isolation_level=None and explicit BEGIN IMMEDIATE/COMMIT/ROLLBACK, separate from the WAL-mode _connect() used for reads, to serialize id+hash-chain assignment against concurrent writers"
  - "verify_chain(start_id=...) seeds expected_prev_hash from the row immediately preceding start_id when start_id > 1, so partial-range verification still validates chain linkage rather than only intra-range hashes"

requirements-completed: ["REQ-010"]

# Metrics
duration: 12min
completed: 2026-08-13
---

# Phase 7 Plan 1: Audit Trail Foundation Summary

**Append-only, hash-chained SQLite `audit_events` store (shared/audit) with unconditional secret redaction, fail-closed writes, and contextvar-backed actor identity — the primitive every later audit capture path (decorator, dual-write, chat tools) plugs into.**

## Performance

- **Duration:** ~12 min
- **Started:** 2026-08-13T00:35:00Z (approx, worktree base commit)
- **Completed:** 2026-08-13
- **Tasks:** 2/2
- **Files modified:** 6 (5 created, 1 modified)

## Accomplishments
- `AuditStore` with `record/query/count/iter_events/verify_chain` — append-only via two `RAISE(ABORT)` triggers, tamper-evident via a SHA-256 `prev_hash`/`row_hash` chain from a `"0"*64` genesis constant
- `record()` is fail-closed: any exception (including read-only-DB writes) raises `AuditWriteError`, never silently swallowed (D-03)
- `redact()` deep-redacts secret-keyed dict values (api_key/secret/token/password/credential/authorization/private_key patterns) unconditionally at the store layer, with stable SHA-256 fingerprints for change detection without disclosure (D-04)
- `ActorContext` + `set_actor/reset_actor/get_actor/actor_context()` + `AuditContextMiddleware` provide ambient actor identity, verified to propagate correctly across `ThreadPoolExecutor` via `contextvars.copy_context()`
- 17-test unit suite covering trigger enforcement, chain integrity, tamper detection (exact `first_invalid_id`), nested redaction, fail-closed writes, 2-process x 50-write concurrency (100 contiguous ids, valid chain), actor-context roundtrip/propagation, and the Phase-8 D-06 `module_approved`/`bundle_sha256` event shape
- `make audit-test` target added to Makefile (after `auth-test`, `.PHONY` updated)

## Task Commits

Each task was committed atomically:

1. **Task 1: shared/audit package — store, redaction, context** - `3911c5a` (feat)
2. **Task 2: Unit test suite + Makefile target** - `a57a411` (test)

**Plan metadata:** (pending — orchestrator commits SUMMARY.md separately after wave merge)

## Files Created/Modified
- `shared/audit/store.py` - `AuditStore` (append-only, hash-chained, WAL SQLite), `AuditWriteError`, `ChainVerificationResult`, `get_audit_store`/`set_audit_store` singleton
- `shared/audit/redaction.py` - `redact()` deep secret redaction, `fingerprint()` SHA-256 helper
- `shared/audit/context.py` - `ActorContext`, contextvar accessors, `actor_context()`, `AuditContextMiddleware`
- `shared/audit/__init__.py` - package re-exports
- `tests/unit/test_audit_store.py` - 17-test suite (triggers, chain, tamper, redaction, fail-closed, concurrency, context, D-06)
- `Makefile` - `audit-test` target + `.PHONY` entry

## Decisions Made
- Mirrored `shared/billing/usage_store.py` connection conventions (`Path(db_path)`, `parent.mkdir`, WAL, `busy_timeout=10000`) for reads/init, but `record()` uses a dedicated `isolation_level=None` connection with explicit `BEGIN IMMEDIATE` to correctly serialize id assignment and hash-chain reads against concurrent writer processes — a WAL-mode `with self._connect()` implicit transaction would not have provided the same write-lock-up-front guarantee.
- `verify_chain()` accepts optional `start_id`/`end_id` for partial-range checks; when `start_id > 1` it fetches the preceding row's `row_hash` to seed `expected_prev_hash`, so a partial scan still validates chain linkage into the unscanned prefix rather than only checking internal consistency of the given range.
- Filter keys for `query`/`count`/`iter_events` are validated against an explicit allow-list (`org_id`, `actor_id`, `action`, `resource_type`, `resource_id`, plus `start_time`/`end_time`/`since`/`until` range aliases on `timestamp`) — unknown filter keys raise `ValueError` rather than being silently ignored or passed through to SQL.

## Deviations from Plan

None - plan executed exactly as written. One self-caught adjustment during Task 1 verification: the module docstring in `store.py` originally contained the literal substring `RAISE(ABORT)` in prose, which pushed `grep -c "RAISE(ABORT" shared/audit/store.py` to 3 instead of the plan's specified 2 (the two trigger definitions). Reworded the docstring line to describe trigger behavior without the literal string before committing Task 1 — not logged as a Rule 1-3 deviation since it was caught and fixed pre-commit during the plan's own acceptance-criteria verification step, not a bug discovered after the fact.

## Issues Encountered
- Initial version of the threadpool-propagation test double-wrapped `contextvars.Context.run()` (`pool.submit(ctx.run, read_actor)` where `read_actor` itself called `ctx.run(get_actor)`), which raises `RuntimeError: cannot enter context: ... is already entered`. Fixed by submitting `get_actor` directly through `ctx.run` exactly once. Caught during Task 2's own test run before commit.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- `shared/audit.record()` is the underlying primitive Plan 07-02's `@audit_action` decorator and Plan 07-03's query API build on directly — signature already accepts `resource_id`/`before_state`/`after_state`/`ip_address`/`details` per the plan's behavior contract.
- `AuditContextMiddleware` is ready to wire into the Admin API (:8003) and Dashboard (:8001) app instances in 07-02, reading `request.state.user`/`request.state.org_id` set by the existing `APIKeyAuthMiddleware`.
- D-06 cross-phase contract verified: `record(action="module_approved", resource_type="module", details={"bundle_sha256": ..., "timestamp": ...})` round-trips through `query()` with no schema change required — Phase 8's approval events can call this API as-is.
- No blockers. `shared/modules/audit.py` (`DevModeAuditLog`, `BuildAuditLog`) is untouched by this plan; the D-01 dual-write shim from `DevModeAuditLog.log_action()` into this new store is scoped to a later plan/task per 07-CONTEXT.md discretion notes.

---
*Phase: 07-audit-trail*
*Completed: 2026-08-13*

## Self-Check: PASSED

All created files verified present on disk (shared/audit/__init__.py, store.py, redaction.py,
context.py, tests/unit/test_audit_store.py, this SUMMARY.md). All task commit hashes
(3911c5a, a57a411, 5594e54) verified present in `git log`.
