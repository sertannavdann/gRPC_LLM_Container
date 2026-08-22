---
phase: 08-co-evolution-approval
plan: 12
subsystem: ui
tags: [fastapi, recharts, react, adapter-run-result, generic-renderer]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "Phase 3 plan 01 AdapterRunResult contract (shared/modules/output_contract.py), 08-03 pending_approval/status/state SSE fields, Phase 6 capability-driven rendering + no-silent-fallback rules"
provides:
  - "GET /modules/{category}/{platform}/run — dashboard endpoint mapping AdapterResult -> canonical AdapterRunResult envelope, authenticated, rate-limited, 404s on approval-gate bypass"
  - "adminApi.runModule(category, platform) typed fetcher + AdapterRunResult/RunDataPoint/RunArtifact/RunError TS types in adminClient.ts"
  - "ModulePanel — generic AdapterRunResult renderer (key/value rows, declared-type chart artifacts, contracted empty/error states)"
  - "NodeDetailPanel wiring: ModulePanel for installed/running module nodes, explicit status line for failed/validating modules, mutually exclusive with the D-09 review surface"
affects: [08-co-evolution-approval-pipeline-ui]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "dashboardFetch() helper in adminClient.ts — same timeout/error-throwing shape as adminFetch, scoped to DASHBOARD_BASE instead of ADMIN_BASE"
    - "Manifest-optional installed check: missing manifest.json means built-in adapter (always runnable), present-but-not-INSTALLED manifest 404s"
    - "Chart artifact type/mime_type trusted verbatim for rendering choice — never inferred from data shape (UI-SPEC Flag 4)"

key-files:
  created:
    - tests/unit/test_module_run_endpoint.py
    - ui_service/src/components/pipeline/ModulePanel.tsx
  modified:
    - dashboard_service/main.py
    - ui_service/src/lib/adminClient.ts
    - ui_service/src/components/pipeline/NodeDetailPanel.tsx

key-decisions:
  - "Credential resolution for the run endpoint reuses _CREDENTIAL_ENV_MAP (built-in adapters) first, falling back to the module CredentialStore (dynamic modules) — no new lookup mechanism"
  - "Truncation metadata (data_points_truncated/data_points_total) lives as extra top-level keys outside the strict Pydantic AdapterRunResult fields — from_dict() ignores unrecognized keys, so the envelope stays contract-valid while still surfacing truncation"
  - "ModulePanel test used the plan's own suggested fallback: mount the real run_module handler onto a minimal FastAPI app with get_current_user overridden, instead of bootstrapping the full auth middleware stack"
  - "Installed/running gate for showing ModulePanel is status==='installed' OR state==='running' — deliberately excludes 'approved' (approved-but-not-yet-installed modules aren't in adapter_registry yet and would 404 on run)"

patterns-established:
  - "D-07 generic module UI: any module's canonical output renders through one shared panel; modules never ship their own UI code"

requirements-completed: ["REQ-014"]

# Metrics
duration: ~55min
completed: 2026-08-22
---

# Phase 08 Plan 12: Generic Module Output Panel (D-07) Summary

**Dashboard `GET /modules/{category}/{platform}/run` endpoint mapping adapter fetches into the canonical `AdapterRunResult` envelope, paired with a generic `ModulePanel` React component that renders any installed module's data/charts/empty/error states with zero module-specific UI code.**

## Performance

- **Duration:** ~55 min
- **Completed:** 2026-08-22T08:10:18Z
- **Tasks:** 3/3 completed
- **Files modified:** 5 (2 created, 3 modified)

## Accomplishments
- `AdapterRunResult` — defined since Phase 3 but never produced anywhere in the running system — now has a real data source: the dashboard run endpoint maps `AdapterResult` (success/failure) into the canonical envelope with `RunMetadata`, `DataPoint`, `AdapterError`, `MeteringData`, timing the fetch with `time.perf_counter()`.
- The approval gate is not bypassable through the run path: a manifest present but not `ModuleStatus.INSTALLED` 404s, closing T-08-49.
- A single generic `ModulePanel` component consumes the envelope for ANY module — key/value data-point rows grouped by `schema_ref`, chart artifacts rendered strictly from their declared `type`/`mime_type` (never data-shape sniffing, UI-SPEC Flag 4), non-chart artifacts as a labelled name+size row, and the exact contracted `EmptyState` copy when both `data_points` and `artifacts` are empty.
- `NodeDetailPanel` now shows `ModulePanel` for installed/running module nodes and an explicit status line for failed/validating nodes — the panel body is never left blank for a module node (Phase 6 no-silent-fallback), and the D-09 review surface remains mutually exclusive with the output panel.

## Task Commits

Each task was committed atomically:

1. **Task 1: Dashboard run endpoint emitting AdapterRunResult** - `712d2f0` (feat)
2. **Task 2: Generic ModulePanel renderer + typed fetcher** - `12bca1d` (feat)
3. **Task 3: Surface ModulePanel for installed modules in the detail panel** - `6cfcc74` (feat)

_Note: `tdd="true"` on Task 1 followed the plan's RED→GREEN flow — `tests/unit/test_module_run_endpoint.py` was written and run to a confirmed failure (`AttributeError: module 'dashboard_service.main' has no attribute 'run_module'`) before the handler was implemented; both are folded into the single Task 1 commit alongside the passing implementation, consistent with 08-03's "test-alongside-implementation" precedent for additive, no-prior-behavior-to-regress endpoints._

## Files Created/Modified
- `dashboard_service/main.py` — `GET /modules/{category}/{platform}/run`, `_load_module_manifest()`, `_resolve_module_run_credentials()`; NOT added to `public_paths` (authenticated + rate-limited)
- `tests/unit/test_module_run_endpoint.py` — 8 tests: success/failure round-trip through `AdapterRunResult.from_dict()`, module_id/capability/duration_ms assertions, unregistered-adapter 404, manifest-present-but-not-installed 404
- `ui_service/src/lib/adminClient.ts` — `RunDataPoint`/`RunArtifact`/`RunError`/`RunMetadata`/`RunMetering`/`AdapterRunResult` TS types, `dashboardFetch()` helper, `adminApi.runModule(category, platform)`
- `ui_service/src/components/pipeline/ModulePanel.tsx` — generic renderer: user-initiated "Run module" button, `DataPointRows`, `ChartArtifact` (Recharts `BarChart` + SSR-safe `ResponsiveContainer`/`initialDimension`), `ArtifactRow`, `DegradedBanner`/`EmptyState` wiring
- `ui_service/src/components/pipeline/NodeDetailPanel.tsx` — `showModulePanel`/`showModuleUnavailableNotice` gates, `<ModulePanel>` wired below the Status section, explicit status line for failed/validating modules

## Decisions Made
- Credential resolution reuses the existing `_CREDENTIAL_ENV_MAP` path (built-in adapters: openweather/google_calendar/clashroyale) first, then falls back to the encrypted module `CredentialStore` for dynamically-built modules — matches the plan's "reuse the same mechanism, don't invent a new one" instruction while still covering all installable module types.
- `data_points` truncation (cap 200) is recorded as extra top-level dict keys on the JSON response rather than inside the strict Pydantic model fields, since neither `RunMetadata` nor `MeteringData` has a free-form metadata field — `AdapterRunResult.from_dict()` ignores unrecognized keys by default, so the envelope stays valid.
- Test file mounts the real `run_module` function (imported from `dashboard_service.main`, still the actual production object since FastAPI's route decorator returns the undecorated function) onto a fresh minimal `FastAPI()` app with `get_current_user` overridden via `dependency_overrides` — avoids bootstrapping the full `APIKeyAuthMiddleware`/rate-limit/OTel stack per the plan's own suggested fallback.
- `showModulePanel` gate is `status === 'installed' || state === 'running'`, deliberately excluding `status === 'approved'` — an approved-but-not-yet-installed module isn't in `adapter_registry` yet and would 404 on the run endpoint if surfaced.

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<action>`/`<behavior>` specifications were followed directly; no Rule 1-4 auto-fixes were needed.

## Issues Encountered

The worktree's initial HEAD was on an unrelated stale commit (`6b2027b`, "Cohesion (#14)") rather than the expected base `930972c` (which carries all of Phase 08 through wave 4). The mandatory `worktree_branch_check` step's `git reset --hard 930972c...` succeeded on the first attempt with a clean working tree — no repository state was lost.

`ui_service/node_modules` was absent at plan start (per coordination notes) — resolved with `npm ci` before running `tsc`/`next lint`/`npm run build`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- D-07 is fully delivered end-to-end: backend envelope production, typed frontend fetcher, generic renderer, and detail-panel wiring all ship in this plan with no stubs.
- `ModulePanel`'s `ChartArtifact` renderer currently supports one chart shape (bar chart from a JSON array of `{name, value}` rows) since no adapter in the current registry emits `artifacts` yet — `AdapterResult` -> `AdapterRunResult` mapping intentionally leaves `artifacts=[]` (adapters don't produce artifacts today, per Task 1's `<action>`). A future module that emits chart artifacts is the natural next consumer/validator of the `ChartArtifact` branch.
- Manual verification (services up, selecting an installed module node in the live pipeline UI) was not performed in this worktree-isolated execution — `python -m pytest tests/unit/test_module_run_endpoint.py -q` and `cd ui_service && npm run build` both pass, satisfying the plan's automated verification gates.
- No blockers for the concurrently-running plan 08-11 (chat ActionCard / ModuleAdminTool) — this plan touched only `dashboard_service/main.py`, `ui_service/src/lib/adminClient.ts`, and the pipeline component directory, per the disjoint-files instruction.

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-22*

## Self-Check: PASSED

- FOUND: dashboard_service/main.py (GET /modules/{category}/{platform}/run)
- FOUND: tests/unit/test_module_run_endpoint.py
- FOUND: ui_service/src/lib/adminClient.ts (runModule)
- FOUND: ui_service/src/components/pipeline/ModulePanel.tsx
- FOUND: ui_service/src/components/pipeline/NodeDetailPanel.tsx (ModulePanel wiring)
- FOUND: commit 712d2f0 (Task 1)
- FOUND: commit 12bca1d (Task 2)
- FOUND: commit 6cfcc74 (Task 3)
