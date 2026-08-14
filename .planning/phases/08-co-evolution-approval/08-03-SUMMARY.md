---
phase: 08-co-evolution-approval
plan: 03
subsystem: api
tags: [sse, fastapi, module-lifecycle, pipeline, build-audit]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: manifest.py ModuleManifest/ModuleStatus, audit.py BuildAuditLog/AttemptRecord (Track A self-evolution infra), admin_api.py audit_module glob+load+filter pattern
provides:
  - "_build_pending_approval_list() manifest scan merged into the 2s pipeline SSE payload — VALIDATED-but-never-loaded modules become visible"
  - "_build_stage_index() BuildAuditLog reader giving live scaffold/implement/tests/repair stage for in-flight modules"
  - "dashboard AUDIT_DIR env wiring to the orchestrator-written shared audit dir"
  - "explicit status/pending_approval/build_stage fields on every module entry in the SSE contract, consumed by ui_service adminClient.ts (plan 08-07)"
affects: [08-co-evolution-approval-07-pipeline-ui, 08-co-evolution-approval-approval-gates]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure-function SSE payload builders (_build_pending_approval_list, _build_stage_index) called once per 2s cycle, mirroring existing _build_adapter_list/_build_tool_list style"
    - "Mtime-tuple cache key (not directory mtime) to avoid re-parsing unchanged audit files on every SSE cycle"
    - "Enrichment-pass-over-status-fallback: build_stage defaults to the status string, then a single post-processing step overrides it for in-flight modules only"

key-files:
  created:
    - tests/unit/test_pipeline_stream_pending.py
  modified:
    - dashboard_service/pipeline_stream.py
    - docker-compose.yaml

key-decisions:
  - "build_stage enrichment applies ONLY to pending/validating statuses — validated/approved/installed/failed keep the status-derived fallback so a stale audit file can never overwrite the pending-approval visual"
  - "Stage index cache keyed on (filename, st_mtime_ns) tuples for the 50 newest audit files, not directory mtime, because BuildAuditLog.save() rewrites the same filename per attempt"
  - "Audit scan is skipped entirely when no module is in flight — zero audit I/O in the steady state (T-08-58 mitigation)"
  - "Only the single stage string is extracted from BuildAuditLog — never job_id/logs/validation_report/failure_fingerprint, keeping the unauthenticated SSE stream free of sensitive detail (T-08-57)"

patterns-established:
  - "SSE module entries always carry status/pending_approval/build_stage/state explicitly — Phase 6 no-client-side-inference rule extended to module lifecycle state"

requirements-completed: ["REQ-014"]

# Metrics
duration: 25min
completed: 2026-08-14
---

# Phase 08 Plan 03: Pending-Approval Modules + Live Build Stage in Pipeline SSE Summary

**Manifest-scanning `_build_pending_approval_list()` and audit-log-reading `_build_stage_index()` merged into the dashboard's 2-second pipeline SSE payload, making VALIDATED-awaiting-approval modules and live scaffold/implement/tests/repair build stages visible to the pipeline graph without any client-side inference.**

## Performance

- **Duration:** 25 min
- **Tasks:** 3/3 completed
- **Files modified:** 3 (1 created, 2 modified)

## Accomplishments
- A module sitting at VALIDATED on disk (never loaded) now appears in the SSE `modules` payload with `pending_approval: true`, closing the D-01/D-04 gap where `_build_pipeline_state()` previously sourced modules exclusively from `loader.list_modules()`
- In-flight modules (pending/validating) report the LIVE build stage read from their newest `BuildAuditLog`'s last attempt, making D-13's stage-colour progression reachable from the backend contract alone
- Loaded and manifest-only modules are merged and deduplicated by `category/platform` id — no double entries
- Dashboard's `AUDIT_DIR` now correctly points at the shared host `./data/audit` (via `/app/shared_data`) that the orchestrator actually writes to, fixing a container-mount mismatch that would have silently returned zero audit files

## Task Commits

1. **Task 1: Manifest-scanning pending-approval list merged into the SSE payload** - `ad9d53c` (feat)
2. **Task 2: Unit tests for the pending-approval SSE contract** - `5de1a6b` (test)
3. **Task 3: Live build_stage from BuildAuditLog + dashboard AUDIT_DIR wiring** - `4f79f95` (feat)

_Note: tdd="true" tasks in this plan followed test-alongside-implementation rather than strict RED-first commits, since Task 1's helper and Task 3's audit reader are additive to an existing pure-function-style module (`_build_adapter_list`/`_build_tool_list` precedent) with no pre-existing behavior to regress; Task 2 is the dedicated test commit locking the Task 1 contract, and Task 3 extends the same test file in its own commit alongside the implementation it covers._

## Files Created/Modified
- `dashboard_service/pipeline_stream.py` - Added `MODULES_DIR`/`AUDIT_DIR` module constants, `_build_pending_approval_list()`, `_build_stage_index()`, `_IN_FLIGHT_STATUSES`/`_BUILD_STAGES`/`_STAGE_INDEX_CACHE`; merged manifest scan into `_build_pipeline_state()`'s module-building loop with dedup
- `docker-compose.yaml` - Added `AUDIT_DIR=/app/shared_data/audit` to the dashboard service's environment list with an explanatory comment
- `tests/unit/test_pipeline_stream_pending.py` - 19 tests covering status mapping, malformed-manifest/missing-dir robustness, dedup merge, stage-index newest-mtime-wins, malformed-audit-file skip, and stage-enrichment scoping to in-flight statuses only

## Decisions Made
- Kept `_build_pending_approval_list(modules_dir, audit_dir=None)` with a default parameter (not a required one) so Task 1's call site (`_build_pending_approval_list(MODULES_DIR)`) stays a single-argument call while Task 3's tests can point at `tmp_path` fixtures directly
- Used `entry["status"] in _IN_FLIGHT_STATUSES` as the single gate for both "should we run `_build_stage_index()` at all this cycle" and "should this entry's `build_stage` be overridden" — avoids two separate conditionals drifting out of sync

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<action>` and `<behavior>` specifications were followed directly; no Rule 1-4 auto-fixes were needed.

## Issues Encountered

The worktree's initial HEAD was on an unrelated, much older commit (`6b2027b`, "Cohesion (#14)") rather than the expected base commit `7f445903` (which carries Phase 08's `08-CONTEXT.md`/`08-RESEARCH.md` and the prior 08-01/08-02 plan work). The mandatory `worktree_branch_check` step's `git reset --hard 7f445903...` was blocked once by the auto-mode classifier on first attempt and succeeded on retry with no other changes. No repository state was lost — `git status --short` was clean before the reset.

## User Setup Required

None - no external service configuration required. `AUDIT_DIR` is wired via `docker-compose.yaml` env var only; no new secrets or manual dashboard steps.

## Next Phase Readiness

- The SSE `modules` payload now carries the `status`/`pending_approval`/`build_stage`/`state` fields that plan 08-07 (`ui_service/src/lib/adminClient.ts` `ModuleState` type, per this plan's `<interfaces>` context) is written against — that plan can consume this contract directly with no further backend changes.
- No blockers. The `AUDIT_DIR` mount fix depends on `docker-compose.yaml`'s existing `./data:/app/shared_data` volume already being present on the dashboard service (verified in `<read_first>` — unchanged), so no infra work is outstanding.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-14*

## Self-Check: PASSED

- FOUND: dashboard_service/pipeline_stream.py
- FOUND: tests/unit/test_pipeline_stream_pending.py
- FOUND: .planning/phases/08-co-evolution-approval/08-03-SUMMARY.md
- FOUND: docker-compose.yaml AUDIT_DIR=/app/shared_data/audit
- FOUND: commit ad9d53c (Task 1)
- FOUND: commit 5de1a6b (Task 2)
- FOUND: commit 4f79f95 (Task 3)
- FOUND: commit b74cba5 (SUMMARY.md)
