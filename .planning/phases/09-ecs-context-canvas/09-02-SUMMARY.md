---
phase: 09-ecs-context-canvas
plan: 02
subsystem: dashboard-context-api
tags: [fastapi, pytest, verbalizer, context-bridge]

requires: ["ui_service/src/ecs/types.ts (c_state DSL grammar contract, plan 01)"]
provides:
  - "dashboard_service/canvas_context.py — Python port of canonicalize()/to_compact_dsl() + pipeline_state_to_views() adapter"
  - "GET /context/canvas — public route returning compact-DSL c_state, registered before /context/{category}"
affects: ["09-ecs-context-canvas plan 03 (TS verbalizer port, diffed against this output)", "orchestrator ContextBridge (future canvas-context consumer)"]

tech-stack:
  added: []
  patterns:
    - "Server-side re-derivation of browser-owned state from an existing backend-computed dict, instead of adding a stateful ingestion endpoint"
    - "Degrade-per-collection-never-raise convention (mirrors _build_pending_approval_list) applied to a new flattening adapter"

key-files:
  created:
    - dashboard_service/canvas_context.py
    - tests/unit/test_canvas_context.py
  modified:
    - dashboard_service/main.py

key-decisions:
  - "T-09-04: /context/canvas stays PUBLIC, inheriting the existing '/context' public_paths prefix — identical posture to /context/{category} and the already-public /stream/pipeline-state, which broadcasts the same source dict. Mitigation applied at the payload layer instead: canvas_context.py emits zero credential names/values, only auth_required/no_credentials flags."
  - "Route registered before /context/{category} (FastAPI matches by registration order) so 'canvas' is never captured by the category path param and 400'd against valid_categories."

requirements-completed: [D9-06, D9-DISCRETION-CSTATE-SEAM, T-09-04]

duration: 35min
completed: 2026-09-16
---

# Phase 9 Plan 02: Canvas Context Backend Seam Summary

**Python port of the canonical c_state verbalizer plus a public `GET /context/canvas` route lets the orchestrator read canvas state from the dashboard's existing 2-second SSE builder — no browser tab required.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (all auto)
- **Files modified:** 3 (2 created, 1 modified)

## Accomplishments

- Ported `canonicalize()` and `to_compact_dsl()` field-for-field from `.planning/spikes/006-delta-context-streaming/verbalize.mjs`, matching the c_state DSL grammar declared in `ui_service/src/ecs/types.ts`
- Built `pipeline_state_to_views()`, the flattening adapter with no existing Python analog — maps `services`/`modules`/`adapters`/`tools`/`stage_tools` from `_build_pipeline_state()`'s dict into canonical view records using the same logical ids the React Flow page already uses (`svc-`, `module-`, `adapter-`, `tool-`, `stage-`)
- Every collection loop degrades to a skip-and-log on unexpected failure rather than raising, matching `_build_pending_approval_list`'s established convention for code inside the 2-second SSE cycle path
- Registered `GET /context/canvas` immediately before `GET /context/{category}` in `dashboard_service/main.py`, with the PUBLIC auth posture recorded explicitly in the handler docstring (not left implicit)
- Wrote `tests/unit/test_canvas_context.py`: 6 tests covering header/grouping, byte-stability across shuffled/reversed input, rounded-int latency rendering, absence of credential material, malformed-state degradation, and route-registration order (via `TestClient`)
- Full suite run (`test_canvas_context.py` + `test_pipeline_stream_pending.py`) — 25 passed, no regression in the sibling SSE contract

## Task Commits

1. **Task 1: Port the canonical verbalizer to Python** — `14d97c8` (feat)
2. **Task 2: Register GET /context/canvas ahead of the /context/{category} route** — `8415284` (feat)
3. **Task 3: Pytest suite — byte-stability, ordering independence, no secret leakage** — `10e944f` (test)

**Plan metadata:** committed alongside this SUMMARY (worktree mode — orchestrator handles STATE.md/ROADMAP.md after the wave completes)

## Sample c_state Output (first 10 lines, from test fixture)

```
# pipeline_state — line format: <id> "<label>" <status>[/<lifecycle>][ detail=<detail>][ latency=<ms>][ creds:<c1,c2>][ flags:<f1,f2>]
[adapter]
adapter-calendar/google_calendar "Google Calendar" error detail=calendar/google_calendar flags:auth_required,no_credentials
adapter-finance/cibc "CIBC" running detail=finance/cibc
[module]
module-finance/cibc "CIBC" running/installed detail=installed
module-gaming/clashroyale "Clash Royale" disabled/validated detail=validating flags:pending_approval
module-weather/openweather "OpenWeather" running/installed detail=installed
[service]
svc-dashboard "dashboard" running latency=0
```

This sample is provided so plan 03's TS verbalizer port can be diffed against it for grammar parity.

## Files Created/Modified

- `dashboard_service/canvas_context.py` — `canonicalize()`, `pipeline_state_to_views()`, `to_compact_dsl()`, `build_canvas_context()`
- `dashboard_service/main.py` — added `GET /context/canvas` handler + imports (`_build_pipeline_state`, `build_canvas_context`), registered before `/context/{category}`
- `tests/unit/test_canvas_context.py` — 6 pytest tests

## Decisions Made

- **T-09-04 (Information Disclosure):** `/context/canvas` stays public via the existing `/context` prefix entry — gating it alone would add no confidentiality since `/stream/pipeline-state` already broadcasts the same source dict publicly. Mitigation is at the payload layer: `creds` is always `[]`; presence/absence of credentials is conveyed only via `auth_required`/`no_credentials` flags. This decision is recorded in the handler docstring, per the plan's explicit requirement that the auth posture not be an accident of prefix matching.
- Route ordering: `/context/canvas` registered textually before `/context/{category}` in `main.py`, confirmed via `grep -n` line-number comparison and via `app.router.routes` index comparison in `test_route_registered_before_category`.

## Deviations from Plan

None — plan executed exactly as written. The verify command in Task 1 (`python -c "from dashboard_service.canvas_context import ..."` run from `tests/`) requires `PYTHONPATH` to include the repo root; this repo's actual convention (confirmed via Makefile) always runs tests via `python -m pytest`, which picks up `tests/conftest.py`'s `sys.path.insert(0, PROJECT_ROOT)`. Verified the module imports correctly under that convention rather than a bare `python -c` with no path setup — not a plan deviation, just how the verify command was actually exercised.

## Issues Encountered

None blocking. One self-caught test bug: an early draft of `test_latency_rendered_as_rounded_int` had a tautological assertion (`"..." in text + " " or text.endswith(...)`, which is always true); fixed to assert the exact rendered substring before finalizing the test suite commit.

## User Setup Required

None.

## Next Phase Readiness

- `build_canvas_context()` is ready for `orchestrator/context_bridge.py` (or equivalent) to call via `GET {dashboard_url}/context/canvas` with no browser dependency.
- The sample c_state text above is available for plan 03's TypeScript verbalizer port to diff against for grammar parity.
- No blockers for downstream Phase 9 plans.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

- FOUND: dashboard_service/canvas_context.py
- FOUND: tests/unit/test_canvas_context.py
- FOUND: dashboard_service/main.py (modified)
- FOUND: commit 14d97c8
- FOUND: commit 8415284
- FOUND: commit 10e944f
