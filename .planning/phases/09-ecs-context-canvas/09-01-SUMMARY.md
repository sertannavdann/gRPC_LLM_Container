---
phase: 09-ecs-context-canvas
plan: 01
subsystem: testing
tags: [vitest, vite-tsconfig-paths, miniplex, miniplex-react, zod, typescript, ecs]

requires: []
provides:
  - Vitest unit-test runner for ui_service (node environment, no watch mode)
  - miniplex, miniplex-react, zod installed at audited versions
  - ui_service/src/ecs/types.ts — canonical EntityRecord/CanvasView/Kind/Status/Lifecycle vocabulary, entityIdFor(), c_state DSL grammar contract
affects: [09-ecs-context-canvas plans 02-10]

tech-stack:
  added: [vitest@5.0.1, vite-tsconfig-paths@6.1.1, miniplex@2.0.0, miniplex-react@2.0.1, zod@4.6.5]
  patterns: ["shared ECS type contract module imported by all downstream Phase 9 plans", "c_state DSL grammar declared once as a doc-comment contract"]

key-files:
  created:
    - ui_service/vitest.config.ts
    - ui_service/src/ecs/types.ts
    - ui_service/src/ecs/__tests__/types.test.ts
  modified:
    - ui_service/package.json
    - ui_service/package-lock.json

key-decisions:
  - "Vitest + vite-tsconfig-paths approved by human via package-legitimacy checkpoint (npmjs.com downloads/repo/publish-date confirmed) — no substitute runner needed"
  - "STATUSES includes 'idle' (not mapped to 'unknown') because the production ServiceState union ('running'|'error'|'idle') requires it — test reflects reality per plan instruction"
  - "globals: false in vitest.config.ts — every test file imports describe/it/expect explicitly from vitest, avoiding an ambient-global types entry in tsconfig.json that could break next build"

patterns-established:
  - "Every file in ui_service/src/ecs/ carries its own 'use client' directive"
  - "npm scripts always invoke vitest via 'run' subcommand — never bare watch-mode vitest"

requirements-completed: [D9-01, D9-06, VAL-W0-RUNNER]

duration: 25min
completed: 2026-09-16
---

# Phase 9 Plan 01: ECS Wave 0 Runner + Type Contract Summary

**Vitest unit-test runner stood up for ui_service (previously zero unit-test infra), plus the shared ECS entity/view/id/DSL contract (`src/ecs/types.ts`) that all Phase 9 plans 02-10 import.**

## Performance

- **Duration:** ~25 min (including a blocking package-legitimacy checkpoint pause)
- **Started:** 2026-09-15T18:35:00Z (approx, checkpoint pause included)
- **Completed:** 2026-09-16T02:43:00Z
- **Tasks:** 3 (1 checkpoint + 2 auto)
- **Files modified:** 5

## Accomplishments
- Installed `vitest` + `vite-tsconfig-paths` after explicit human approval via the package-legitimacy checkpoint (Task 1)
- Configured `ui_service/vitest.config.ts` (node environment, `@/*` path resolution via `vite-tsconfig-paths`, `globals: false`, no watch mode) and added `npm run test` / `npm run test:ecs` scripts
- Installed `miniplex@2.0.0`, `miniplex-react@2.0.1`, `zod` at the versions audited in `09-RESEARCH.md`
- Created `ui_service/src/ecs/types.ts`: `KINDS`/`STATUSES`/`LIFECYCLES` vocabulary, `EntityRecord`/`CanvasView` types, `entityIdFor()` matching the existing React Flow node id scheme (`svc-`, `tool-`, `adapter-`, `module-`, `stage-`), and the c_state DSL grammar contract comment
- Proved the runner with `ui_service/src/ecs/__tests__/types.test.ts` (5 passing assertions)

## Task Commits

Each task was committed atomically:

1. **Task 1: Package legitimacy gate** — checkpoint only, no commit (human approved "vitest confirmed as the runner")
2. **Task 2: Install dependencies and configure the unit runner** - `54ffb86` (feat)
3. **Task 3: Write the shared ECS contract (types.ts) and prove the runner** - `89be31e` (feat)

**Plan metadata:** committed alongside this SUMMARY (worktree mode — orchestrator handles final STATE.md/ROADMAP.md updates after wave completes)

## Files Created/Modified
- `ui_service/vitest.config.ts` - Vitest config: node env, `tsconfigPaths()` plugin, `include: ['src/**/*.test.ts']`, `globals: false`
- `ui_service/src/ecs/types.ts` - Canonical entity/view/id vocabulary + c_state DSL grammar contract for plans 02-10
- `ui_service/src/ecs/__tests__/types.test.ts` - 5 assertions: id scheme (service/module/adapter/tool/stage), KINDS ascending order, STATUSES production coverage
- `ui_service/package.json` - Added `miniplex`, `miniplex-react`, `zod` to `dependencies`; `vitest`, `vite-tsconfig-paths` to `devDependencies`; `test`/`test:ecs` scripts
- `ui_service/package-lock.json` - Lockfile update from npm install

## Decisions Made
- Vitest + vite-tsconfig-paths were approved by the user via the blocking package-legitimacy checkpoint (confirmed npmjs.com downloads, repo ownership, recent publish dates) — no substitute runner was needed, so Tasks 2-3 proceeded exactly as planned.
- Added `'idle'` to `STATUSES` (not mapped to `'unknown'`) because the real `ServiceState.state` union in `ui_service/src/lib/adminClient.ts` includes `'idle'` and the test must reflect production reality, per explicit plan instruction.

## Deviations from Plan

None - plan executed exactly as written (including the required checkpoint gate).

## Issues Encountered
- The worktree's initial base commit did not match the expected wave base commit (`6c25272`) — the worktree had branched from an older, unrelated point in history. Corrected via `git reset --hard 6c25272caafca431c6ddef8b410ebc3f95f89529` per the `<worktree_branch_check>` protocol before any plan work began. No plan files were affected.
- `ui_service/tsconfig.tsbuildinfo` (a tracked build artifact) was touched by the local `tsc --noEmit` verification run; reverted with `git checkout -- ui_service/tsconfig.tsbuildinfo` before committing Task 3 since it's unrelated to this task's scope.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- `ui_service/src/ecs/types.ts` is ready to be imported by plan 02 (Python c_state port), plan 03 (TS verbalizer), and all subsequent Phase 9 plans via `import type { EntityRecord, CanvasView } from '@/ecs/types'`.
- `npm run test` / `npm run test:ecs` are available for all future ECS unit tests in `ui_service`.
- No blockers for Wave 1+ plans in this phase.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

All created files and commit hashes verified present:
- FOUND: ui_service/vitest.config.ts
- FOUND: ui_service/src/ecs/types.ts
- FOUND: ui_service/src/ecs/__tests__/types.test.ts
- FOUND: commit 54ffb86
- FOUND: commit 89be31e
