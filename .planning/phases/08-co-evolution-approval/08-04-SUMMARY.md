---
phase: 08-co-evolution-approval
plan: 04
subsystem: modules
tags: [garbage-collection, retention, billing, background-worker, reference-safety, audit-preservation]

# Dependency graph
requires:
  - phase: 08-02
    provides: shared/modules/gc.py's queue_for_gc() marker-write contract (GC_MARKER_FILENAME, {module_id, rejected_at, actor})
provides:
  - shared/modules/gc.py::sweep_gc_pending() / purge_module_artifacts() — the consumer of 08-02's .gc_pending markers, reference-safe against active_versions (D-12)
  - shared/billing/usage_store.py::delete_before() / list_org_ids() — parameterized per-org deletion primitives
  - orchestrator/retention_worker.py — TIER_RETENTION_DAYS, prune_expired_usage(), gc_and_retention_pass(), gc_and_retention_worker(), start_retention_worker()
  - orchestrator_service.py::serve() startup wiring — one daemon-thread worker running both cleanup policies daily (D-11)
affects: [08-05, 08-08, 08-09, 08-10, 08-11]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "GC path-containment guard (_resolved_child) — every delete target is Path.resolve()'d and asserted inside modules_dir/artifacts_dir before shutil.rmtree, rejecting '..' traversal in module_id (T-08-14)"
    - "Audit-record preservation before rmtree — *.jsonl files inside a directory about to be purged are shutil.copy2'd to modules_dir/.gc_preserved/{category}_{platform}/ first, never deleted (D-10, T-08-15)"
    - "Reference-safety before every delete — version_manager.list_versions()/get_active_version() checked; no version rows means unconditional purge (RESEARCH Pitfall 5), version rows + active pointer means protected (D-12)"
    - "One shared background worker, two independently fault-isolated policies (D-11) — gc_and_retention_pass() wraps each policy in its own try/except so one failing policy never suppresses the other"
    - "Daemon-thread-owns-its-own-asyncio-loop pattern (mirrors admin_api.start_admin_server) — orchestrator_service.serve() is synchronous grpc with no asyncio loop, so start_retention_worker() spawns threading.Thread(target=lambda: asyncio.run(...))"
    - "Reuse over reconstruction — retention worker startup reuses orchestrator_service._usage_store, the already-built _version_manager, and admin_api._api_key_store (set as a module global by start_admin_server before it returns) rather than constructing second instances"

key-files:
  created:
    - tests/unit/modules/test_artifact_gc.py
    - tests/unit/test_retention_worker.py
    - orchestrator/retention_worker.py
  modified:
    - shared/modules/gc.py
    - shared/billing/usage_store.py
    - orchestrator/orchestrator_service.py

key-decisions:
  - "Artifact bundle directories ARE addressable by module_id: ARTIFACTS_DIR/{category}/{platform} mirrors the modules_dir layout (confirmed via dashboard_service/main.py and admin_api.py chart-serving routes), so purge_module_artifacts() deletes them directly rather than falling back to the plan's 'not_addressable' escape hatch"
  - "api_key_store for the retention worker is sourced from admin_api's module-level _api_key_store global, read immediately after start_admin_server() returns (globals are set synchronously before admin_api spawns its own uvicorn daemon thread) — avoids constructing a second APIKeyStore instance"
  - "Unparseable rejected_at timestamps are parsed once per marker (not only when grace_seconds > 0) so the error is always recorded in sweep_gc_pending()'s summary, while the grace-period skip logic itself only applies when grace_seconds > 0 and parsing succeeded"

patterns-established:
  - "_resolved_child(base, *parts) containment helper in gc.py — reusable pattern for any future filesystem-mutating GC/cleanup code that must guard against path traversal from attacker-influenced identifiers"

requirements-completed: [REQ-017]

# Metrics
duration: 20min
completed: 2026-08-14
---

# Phase 8 Plan 04: Artifact GC Sweep + Tiered Usage Retention Worker Summary

**One shared daemon-thread worker now runs both cleanup policies daily: reference-safe artifact GC for terminally rejected modules (D-10/D-12, T-08-14/15/16 mitigated) and tiered per-org usage retention pruning (REQ-017, free=7d/team=90d/enterprise=unlimited), fault-isolated per policy (D-11).**

## Performance

- **Duration:** ~20 min (context gathering + 3 tasks)
- **Started:** 2026-08-14T06:55:00+03:00 (approx)
- **Completed:** 2026-08-14T07:15:00+03:00
- **Tasks:** 3
- **Files modified:** 6 (3 created, 3 modified)

## Accomplishments
- `shared/modules/gc.py::sweep_gc_pending()` / `purge_module_artifacts()` now actually consume the `.gc_pending` markers written by 08-01/08-02's `queue_for_gc()` — previously a marker-write stub with no consumer
- D-12 reference-safety enforced: a module with an `active_versions` rollback pointer is never deleted; a module with version history but no active pointer is purged; a module with no version rows at all (the common case per RESEARCH Pitfall 5 — `install_module()` never calls `record_version()`) is purged unconditionally
- Audit trail preserved unconditionally (T-08-15): any `*.jsonl` file found inside a module or artifact directory being purged is copied to `modules_dir/.gc_preserved/{category}_{platform}/` before `shutil.rmtree` — the audit DB/dir are never opened or scanned by this module
- Path-traversal guard (T-08-14): every delete target is resolved and asserted inside `modules_dir`/`artifacts_dir` before deletion; `..` in a module_id raises instead of resolving outside the sandbox
- `UsageStore.delete_before()` / `list_org_ids()` added with parameterized SQL only (`org_id = ? AND created_at < ?`), verified against a SQL-injection-style `org_id` in a dedicated regression test
- `orchestrator/retention_worker.py` created: `TIER_RETENTION_DAYS = {"free": 7, "team": 90, "enterprise": -1}` mirroring `quota_manager.TIER_QUOTAS`'s unlimited-sentinel convention; `prune_expired_usage()` resolves each org's plan (defaulting missing orgs to free), skips enterprise entirely, and never raises on a single org's failure
- `gc_and_retention_pass()` runs both policies with independent try/except blocks (verified in tests: a raising GC policy still lets retention run, and vice versa) — D-11's "one worker, two policies, fault-isolated" requirement
- `start_retention_worker()` wired into `orchestrator_service.py::serve()` immediately after `start_admin_server(...)`, gated by `GC_WORKER_ENABLED` (default true), reusing the existing `_usage_store`/`_version_manager` instances and `admin_api`'s already-constructed `_api_key_store` — confirmed no duplicate `VersionManager(` construction site added
- Manually verified end-to-end: `start_retention_worker()` spawns a live daemon thread, logs the configured interval exactly once at startup, and successfully runs one pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Reference-safe artifact GC sweep** - `23b5341` (feat)
2. **Task 2: Tiered usage retention pruning** - `6c875ae` (feat)
3. **Task 3: Shared daily worker loop + orchestrator startup wiring** - `b2e6545` (feat)

## Files Created/Modified
- `shared/modules/gc.py` - added `_resolved_child()` path-containment helper, `purge_module_artifacts()`, `sweep_gc_pending()`; `queue_for_gc()` unchanged; scope-note docstring rewritten now that this plan owns the sweep logic
- `tests/unit/modules/test_artifact_gc.py` - 17 tests: reference-safety (protected/purged/unconditional), jsonl preservation, artifact-bundle removal, path-traversal rejection, sweep aggregation (bad markers, missing dir, grace period), and one test against a real `VersionManager`
- `shared/billing/usage_store.py` - `delete_before(org_id, cutoff)` and `list_org_ids()` added, both using the existing `idx_usage_org_created` index and parameterized SQL
- `orchestrator/retention_worker.py` - new file: `TIER_RETENTION_DAYS`, `prune_expired_usage()`, `gc_and_retention_pass()`, `gc_and_retention_worker()`, `start_retention_worker()`
- `tests/unit/test_retention_worker.py` - 19 tests: tier convention, `delete_before`/`list_org_ids` isolation + SQL-injection regression, `prune_expired_usage` per-tier behavior + missing-org default + per-org fault isolation, `gc_and_retention_pass` fault isolation in both directions, no-manual-"Z"-suffix regression guard
- `orchestrator/orchestrator_service.py` - `serve()` now imports and calls `start_retention_worker(...)` right after `start_admin_server(...)`, passing `MODULES_DIR`/`ARTIFACTS_DIR` env-derived paths and the already-constructed store instances

## Decisions Made
- Artifact bundles ARE addressable by module_id (`ARTIFACTS_DIR/{category}/{platform}`, confirmed against `dashboard_service/main.py` and `admin_api.py`'s existing chart-serving routes), so the plan's "not_addressable" fallback path was not needed — bundles are deleted directly alongside the module directory
- `api_key_store` for the retention worker is read from `admin_api._api_key_store` (a module-level global set synchronously inside `start_admin_server` before its own daemon thread starts) rather than constructing a second `APIKeyStore`
- Unparseable `rejected_at` timestamps are always parsed-and-recorded as an error in `sweep_gc_pending()`, independent of whether `grace_seconds > 0` — this matches the plan's `<behavior>` bullet more literally than gating the parse attempt behind the grace-period branch

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Missing generated gRPC protobuf stubs blocked all orchestrator-package test collection**
- **Found during:** Task 2 verification (`python -m pytest tests/unit/test_retention_worker.py`)
- **Issue:** `orchestrator/__init__.py` imports `orchestrator_service`, which imports `shared.clients.llm_client`, which imports `llm_service.llm_pb2` — none of the `*_pb2.py`/`*_pb2_grpc.py` files exist in this worktree because they are `.gitignore`'d build artifacts (`**/*_pb2.py`, `**/*_pb2_grpc.py`) normally generated at Docker build time via `make proto-gen`, not committed to git.
- **Fix:** Ran `make proto-gen` (uses the already-installed `grpc_tools` against the committed `.proto` source files under `shared/proto/`) to regenerate the stubs locally. This is source-to-artifact regeneration from an already-installed toolchain, not a package-manager install of a new dependency, so it is not subject to the package-install exclusion in Rule 3.
- **Files modified:** None tracked by git — generated files remain gitignored and were not staged or committed.
- **Verification:** `tests/unit/test_retention_worker.py` and `tests/unit/modules/test_artifact_gc.py` both collect and pass (36/36) after regeneration.

---

**Total deviations:** 1 auto-fixed (1 blocking, environment-only — no tracked files changed)
**Impact on plan:** None on shipped code; this was purely a local test-collection prerequisite already assumed present by the plan's `<verify>` commands.

## Issues Encountered

- **`git reset --hard` was required at session start.** The worktree's initial HEAD (`6b2027b5cf796c83f41890844ec9c4fc2f46f0d9`) predated Wave 1's merge and did not contain `shared/modules/gc.py`, `shared/billing/`, or the tracked `.planning/` directory at all — `git merge-base HEAD <expected-base>` showed the expected base was a *descendant* of the stale HEAD, not an ancestor, confirming the worktree had not been advanced to the documented Wave 1 merge point. The mandatory `worktree_branch_check` step's conditional `git reset --hard <expected-base>` corrected this per protocol before any code was read or written; no work was lost (working tree was clean at the time).

## User Setup Required

None — no external service configuration required. `GC_WORKER_ENABLED=true` is the default; operators who want to disable the background worker (e.g. in a test/CI container) can set `GC_WORKER_ENABLED=false`. `GC_INTERVAL_SECONDS` defaults to 86400 (daily) and can be overridden for faster local iteration.

## Next Phase Readiness
- The roadmap done-criterion "traces auto-purge per retention policy" is now implemented end-to-end for usage records; module-artifact GC closes the user's explicitly flagged non-negotiable ("memory management in the overlayed artefacts is an essential problem")
- Downstream plans (08-05 rate limiting, 08-08/08-09 review UI, 08-10/08-11 chat approval) can rely on rejected-module artifacts actually disappearing from disk post-terminal-rejection without any further GC wiring
- No blockers identified for subsequent phase-8 plans

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-14*

## Self-Check: PASSED

All 6 files referenced above (created + modified) confirmed present on disk. All 3 task commit hashes (`23b5341`, `6c875ae`, `b2e6545`) confirmed present in `git log`.
