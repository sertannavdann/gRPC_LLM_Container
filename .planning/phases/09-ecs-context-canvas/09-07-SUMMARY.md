---
phase: 09-ecs-context-canvas
plan: 07
subsystem: ui
tags: [react-flow, miniplex, xstate, ecs, playwright, sse]

requires:
  - phase: 09-ecs-context-canvas
    provides: "canvasWorld/touch()/subscribeWorld bridge (plan 03), syncFromPipeline/toEntityRecords (plan 04), STAGE_NODE_IDS/pipelineNodeIds/clearSelectionIfMissing (plan 06)"
provides:
  - "buildCanvasGraph(pipeline, positions) — pure layout extraction, unit-tested"
  - "page.tsx rewired onto the buffered React Flow pattern: SSE ingestion effect, version-keyed ECS patch effect, drag-stop write-back"
  - "pipeline-ecs-churn.spec.ts — Playwright proof of churn stability, real drag persistence, hover stability, stale-selection clearing in the real page"
affects: [09-08, 09-09, 09-10]

tech-stack:
  added: []
  patterns:
    - "Buffered React Flow: React Flow owns `nodes` via useNodesState; an ECS patch effect keyed on `version` mutates only changed mirrored fields by id and returns the SAME node reference when nothing changed; position writes back to ECS on drag-stop only"
    - "SSE ingestion effect diffs the built node/edge id set against the current buffered set and only calls setNodes/setEdges when topology actually changed"

key-files:
  created:
    - ui_service/src/app/pipeline/canvasGraph.ts
    - ui_service/src/app/pipeline/__tests__/canvasGraph.test.ts
    - ui_service/e2e/pipeline-ecs-churn.spec.ts
  modified:
    - ui_service/src/app/pipeline/page.tsx

key-decisions:
  - "canvasGraph.ts is a byte-equivalent extraction of the prior inline layout math — ids, positions, and data payloads are unchanged (UI-SPEC visual regression lock honored)"
  - "The SSE ingestion effect computes currentEcsPositions from canvasWorld.byId and passes it into buildCanvasGraph so a dragged position (already written into the ECS entity) wins over the freshly computed layout on the next topology rebuild"
  - "dataFromEntity() in page.tsx mirrors ecs/sync.ts's MIRRORED_FIELDS list (label/status/lifecycle/detail/latency/flags) per node type, keeping the patch effect's diff surface identical to what the sync writer actually mutates"
  - "onNodesChange only writes an entity's x/y back to ECS when draggingId.current matches the completed drag's id — guards against a stray non-drag position change event writing back"
  - "E2E: ran the worktree's own page.tsx via `next dev -p 3101` pointed at the docker-compose dashboard on 8001, since the running ui_service container serves the main checkout's image, not this worktree's code — documented as E2E_BASE_URL/E2E_DASHBOARD_URL env overrides"
  - "E2E: added an E2E_MODULES_ROOT env override for the probe manifest path, since a worktree's own modules/ directory is not the one bind-mounted into the dashboard container (the main checkout's is) — defaults to this repo's own modules/ dir for single-checkout CI/production runs"

requirements-completed: [D9-02, D9-03, D9-04, VAL-W0-CHURN-E2E]

duration: 55min
completed: 2026-09-16
---

# Phase 09 Plan 07: ECS-Backed Pipeline Canvas Rewire Summary

**Pipeline canvas re-plumbed onto the ECS world via a buffered React Flow pattern (patch-by-id, never a fresh array), verified against a live docker-compose stack with a real Playwright drag/hover/churn/stale-selection spec.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3
- **Files modified:** 4 (2 created source, 1 created test, 1 created E2E spec, 1 modified page)

## Accomplishments
- Extracted the pipeline canvas's static+dynamic layout math into a pure, unit-tested `buildCanvasGraph()` (5/5 vitest cases pass)
- Rewired `page.tsx` onto the buffered React Flow pattern per the skill blueprint: SSE ingestion effect (topology-diffed), `useSyncExternalStore`-driven ECS patch effect (mutates only changed mirrored fields by id, never `world.entities.map()`), and a drag-stop-only position write-back guarded by a `draggingId` ref
- Wrote and GREEN-verified `pipeline-ecs-churn.spec.ts` against the real running dashboard SSE stream: 4/4 non-disruptive tests pass (churn stability, real-drag position persistence across two SSE ticks, hover stability, DOM-level stale-selection clearing via a throwaway `e2e_probe` module)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extract the layout math into a pure buildCanvasGraph() with a unit test** - `d98785a` (feat)
2. **Task 2: Rewire page.tsx onto the buffered React Flow pattern** - `e4d671d` (feat)
3. **Task 3: Playwright spec — churn, real drag, hover, and DOM-level stale selection** - `a273475` (test)

## Files Created/Modified
- `ui_service/src/app/pipeline/canvasGraph.ts` - Pure `buildCanvasGraph(pipeline, positions)` layout builder; exports `STAGE_NODES`/`STAGE_EDGES`/edge-style helpers; imports `STAGE_NODE_IDS` from `pipelinePage.ts` rather than redefining
- `ui_service/src/app/pipeline/__tests__/canvasGraph.test.ts` - 5 vitest cases: null-pipeline stage scaffolding, fixture node-id coverage with no dupes, pending-approval leftmost sort, positions-override precedence, layout completeness
- `ui_service/src/app/pipeline/page.tsx` - Replaced the single rebuild `useEffect` with three cooperating pieces: SSE ingestion effect (`buildCanvasGraph` + `syncFromPipeline`, topology-diffed before `setNodes`/`setEdges`), `useSyncExternalStore(subscribeWorld, getWorldVersion, getWorldVersion)` + version-keyed ECS patch effect (`dataFromEntity()` per node type), and `onNodesChange` drag-stop write-back guarded by `draggingId.current === c.id`. Toolbar, `nodeTypes`, `onNodeClick`, `NodeDetailPanel` element untouched (verified via `git diff`)
- `ui_service/e2e/pipeline-ecs-churn.spec.ts` - 5 Playwright tests (4 run by default, 1 gated behind `E2E_ALLOW_RESTART`): sustained-churn stability, real-drag position persistence across 2 SSE ticks, hover stability under churn, e2e_probe manifest lifecycle proving `clearSelectionIfMissing` in the real page, and a restart-recovery test

## Decisions Made
- `canvasGraph.ts`'s builder computes a fresh default layout on every call but lets a `positions` map entry win per-id — this is how a user's ECS-held drag position survives an SSE topology rebuild without the ingestion effect having to special-case "did this id move."
- The patch effect's `dataFromEntity()` switches on `n.type` rather than trying to generically diff every `EntityRecord` field, because each node type's `data` shape (service/tool/adapter/module) only renders a subset of the mirrored ECS fields — this keeps the emitted patch object minimal and avoids spurious re-renders from unrelated field changes.
- Chose to run the worktree's own Next.js dev server on an alternate port (3101) against the shared docker-compose dashboard (8001) for E2E verification, rather than rebuilding the ui_service Docker image from the worktree — faster to verify and the goal (exercise this worktree's page.tsx code against real SSE) was met either way.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Playwright spec used `import.meta.url`, which Playwright's CJS test transform can't parse**
- **Found during:** Task 3, first spec run (`SyntaxError: Cannot use 'import.meta' outside a module`)
- **Issue:** The plan's read_first guidance suggested resolving the repo root via `import.meta.url`/`process.cwd()`, but this Playwright project's test files transpile as CommonJS, not ESM — `import.meta` throws immediately.
- **Fix:** Switched to `__dirname`-based resolution (`path.resolve(__dirname, '..', '..')`), matching how the rest of the project's Node tooling resolves paths.
- **Files modified:** ui_service/e2e/pipeline-ecs-churn.spec.ts
- **Verification:** Spec file loads and all non-disruptive tests execute.
- **Committed in:** a273475 (Task 3 commit)

**2. [Rule 1 - Bug] Test 4 asserted `getByText('E2E Probe')` (display_name), but the panel renders the manifest's `name` field ("probe")**
- **Found during:** Task 3, Test 4 first run
- **Issue:** The node's rendered `data.label` comes from `ModuleState.name` (`toEntityRecords`/`page.tsx`'s module row uses `m.name`), which is the manifest's `name` field — not `display_name`. The panel never surfaces `display_name` anywhere in this flow, so asserting on "E2E Probe" always timed out.
- **Fix:** Scoped the assertion to the detail panel's header `span.font-semibold` element and matched on "probe" (the actual rendered label), with a comment documenting why `display_name` is not used.
- **Files modified:** ui_service/e2e/pipeline-ecs-churn.spec.ts
- **Verification:** Test 4 passes against the live stack.
- **Committed in:** a273475 (Task 3 commit)

**3. [Rule 1 - Bug] `getByRole('alert')` assertion failed against a pre-existing, always-mounted empty toast container unrelated to the probe scenario**
- **Found during:** Task 3, Test 4 second run
- **Issue:** The app always mounts a toast/alert region (`role="alert"`) regardless of whether a toast has content, so `toHaveCount(0)` never held — this element predates this plan and is unrelated to `clearSelectionIfMissing`'s silent-clear contract.
- **Fix:** Removed the `getByRole('alert')` assertion; kept the `getByText(/error/i)` check (which correctly stayed at 0), with a comment explaining the always-mounted toast chrome is out of scope here.
- **Files modified:** ui_service/e2e/pipeline-ecs-churn.spec.ts
- **Verification:** Test 4 passes; no regression in the silent-clear assertion's intent.
- **Committed in:** a273475 (Task 3 commit)

---

**Total deviations:** 3 auto-fixed (all Rule 1 — bugs discovered while getting the new E2E spec green against the real stack)
**Impact on plan:** All three fixes are scoped entirely to the new spec file; no changes to `canvasGraph.ts` or `page.tsx` were needed. No scope creep.

## Issues Encountered

- **Docker Desktop was not running at agent start** — started successfully once probed (`docker compose ps` succeeded on retry); brought up the full stack from the main checkout with `make up` per the parallel-execution guidance (never from the worktree).
- **The running `ui_service` container serves the main checkout's image, not this worktree's `page.tsx`.** Per the parallel-execution guidance, ran the worktree's own `next dev -p 3101` against the shared dashboard (`http://localhost:8001`) and pointed the Playwright run at `E2E_BASE_URL=http://localhost:3101` so the spec actually exercised this plan's code, not the main checkout's.
- **A worktree's own `modules/` directory is not the one bind-mounted into the dashboard container** (the main checkout's `modules/` is, per `docker-compose.yaml`). Added an `E2E_MODULES_ROOT` env override (default: this repo's own `modules/` dir) so Test 4's probe manifest lands in the directory the dashboard actually scans when run from a worktree; a single-checkout CI/production run needs no override.
- **`pipeline-sse.spec.ts`'s pre-existing "error handling on SSE failure" test fails in this environment independent of this plan's changes** — reproduced in isolation (single worker, no churn spec running) with a clean 20s timeout waiting for "Disconnected" after `context.setOffline(true)`. This test file was not modified by this plan and the failure reproduces against the SAME connection-state machine code (`pipelinePageMachine`) this plan did not touch. Filed as a pre-existing environment-specific flake (likely `context.setOffline` + native `EventSource` timing against a `next dev` server rather than the production nginx/Docker image) rather than a regression — out of this plan's file scope (`ui_service/e2e/pipeline-sse.spec.ts` is not in `files_modified`). Logged to `deferred-items.md`.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- The three-effect shape (SSE ingestion / version-keyed ECS patch / drag-stop write-back) is now the canonical pattern in `page.tsx` for plans 08-10 to extend rather than re-derive, per this plan's `<output>` directive.
- `buildCanvasGraph()` is available for any future plan needing the same layout math (e.g. a history/rewind view) without re-deriving it.
- `pipeline-ecs-churn.spec.ts` E2E coverage is real-browser-verified for churn, drag persistence, hover stability, and stale-selection clearing — plan 10's "manual StrictMode check" and the `if (n && entity)` mid-drag-removal edge case (T-09-17, explicitly unverified) remain open per the plan's threat register.
- Pre-existing `pipeline-sse.spec.ts` "error handling" flake needs investigation independent of this plan (see Issues Encountered) — flagged in `deferred-items.md` rather than fixed here (out of scope for this plan's files).

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*
