---
phase: 09-ecs-context-canvas
plan: 06
subsystem: frontend-state
tags: [xstate, pipeline-page, ecs, dangling-reference]

requires: ["09-01"]
provides:
  - "clearSelectionIfMissing action wired into all three SSE_MESSAGE transitions of pipelinePageMachine"
  - "pipelineNodeIds(data: PipelineState): Set<string> — authoritative node-id space builder"
  - "STAGE_NODE_IDS — exported static stage-id constant for plan 07's canvasGraph.ts"
affects: ["09-ecs-context-canvas plan 07 (canvasGraph.ts imports STAGE_NODE_IDS)", "09-ecs-context-canvas plan 09-07 Test 4 (DOM-level counterpart)"]

tech-stack:
  added: []
  patterns: ["re-validate a context-held entity reference against every new snapshot IN THE SAME TRANSITION (spike 002 A/B pattern)"]

key-files:
  created:
    - ui_service/src/machines/__tests__/pipelinePage.test.ts
  modified:
    - ui_service/src/machines/pipelinePage.ts

key-decisions:
  - "STAGE_NODE_IDS and pipelineNodeIds() exported as named signatures: `export const STAGE_NODE_IDS = ['stage-intent','stage-routing','stage-tools','stage-synth'] as const` and `export function pipelineNodeIds(data: PipelineState): Set<string>` — plan 07 imports both rather than redefining"
  - "clearSelectionIfMissing resets the same five fields as the existing clearSelection action (selectedNodeId, selectedModuleId, review, audit, actionError) so a dangling selection cannot leave stale review data rendered (T-09-15)"
  - "Test stubs for loadReview/approveAction/rejectAction use minimal typed fixtures (fakeReview as ModuleReview, fakeApprovalResult: ApprovalResult) rather than `any`, to satisfy pipelinePageMachine.provide()'s strict actor-logic typing"

requirements-completed: [D9-05, T-09-02]

duration: 20min
completed: 2026-09-16
---

# Phase 9 Plan 06: ECS Pipeline Selection Guard Summary

**Added `clearSelectionIfMissing` to the locked XState v5 pipeline page machine, re-validating `selectedNodeId` against every SSE snapshot in the same transition, with a 6-test machine-level A/B proof reproducing the spike-002 dangling-reference finding in production code.**

## Performance

- **Duration:** ~20 min
- **Started:** 2026-09-15T23:31:00Z (approx)
- **Completed:** 2026-09-15T23:51:00Z
- **Tasks:** 2 (both auto)
- **Files modified:** 2 (1 modified, 1 created)

## Accomplishments
- Added `export const STAGE_NODE_IDS` (the four static stage ids from `page.tsx` that never appear in SSE data)
- Added `export function pipelineNodeIds(data: PipelineState): Set<string>` building the authoritative node-id space from a snapshot via `entityIdFor()` from `@/ecs/types`, treating missing collections as empty
- Added `clearSelectionIfMissing` action (modelled on the existing `clearSelection`) that resets `selectedNodeId`, `selectedModuleId`, `review`, `audit`, `actionError` when the selected id is absent from the current snapshot's id space
- Wired the action into all three `SSE_MESSAGE` transitions (`connecting`, `connected`, `reconnecting`) alongside `updatePipeline`
- Wrote `pipelinePage.test.ts` with 6 passing vitest cases: present-entity-keeps-selection, removed-entity-clears-selection, clears-from-reconnecting, static-stage-survives, malformed-snapshot-does-not-throw, `pipelineNodeIds` unit assertion
- Verified via `git diff` that the `selection` and `reviewPanel` region bodies are byte-identical to before — only additive exports, the new action, and the three transition-line edits changed

## Task Commits

Each task was committed atomically:

1. **Task 1: Add clearSelectionIfMissing and wire it into all three SSE_MESSAGE transitions** — `57c60ea` (feat)
2. **Task 2: Machine unit test — A/B proof of the dangling-selection fix** — `dc0a7cb` (test)

**Plan metadata:** committed alongside this SUMMARY (worktree mode — orchestrator handles final STATE.md/ROADMAP.md updates after wave completes)

## Files Created/Modified
- `ui_service/src/machines/pipelinePage.ts` — added `STAGE_NODE_IDS`, `pipelineNodeIds()`, `clearSelectionIfMissing` action; wired into all three `SSE_MESSAGE` transitions
- `ui_service/src/machines/__tests__/pipelinePage.test.ts` — 6 vitest cases proving the A/B claim at the machine level with fully stubbed actors (no `EventSource`/network)

## Decisions Made
- Exported `pipelineNodeIds` and `STAGE_NODE_IDS` exactly as specified in the plan so plan 07's `canvasGraph.ts` can import them without redefinition.
- Used minimal strictly-typed fixtures (`ModuleReview`, `ApprovalResult`, `ModuleAuditAttempt[]`) for the stubbed `loadReview`/`approveAction`/`rejectAction` actors rather than loosely-typed casts — `pipelinePageMachine.provide({...})` enforces exact actor-logic output types, and a loose stub failed `tsc --noEmit`.

## Deviations from Plan

None — plan executed exactly as written. The acceptance-criteria grep counts matched after removing one incidental prose mention of `clearSelectionIfMissing` from a doc comment (replaced with "the clearing guard") so `grep -c "clearSelectionIfMissing"` returns exactly 4 (1 definition + 3 transition wirings) as specified.

## Issues Encountered
- The worktree's initial base commit did not match the expected wave-2 base commit (`c28fb9e`) — merge-base showed an unrelated older ancestor (`6b2027b`). Corrected via `git reset --hard c28fb9e8d4127cd6250094526e04ababf85e3f05` per the `<worktree_branch_check>` protocol before any plan work began.
- `ui_service/tsconfig.tsbuildinfo` (a tracked build artifact) was touched by local `tsc --noEmit` verification runs; reverted with `git checkout -- ui_service/tsconfig.tsbuildinfo` before each commit since it's unrelated to this plan's scope.
- `ui_service/node_modules` was absent in the fresh worktree; ran `npm install --no-fund --no-audit` before any verification per the parallel-execution note.

## User Setup Required

None.

## Next Phase Readiness
- Plan 07's `canvasGraph.ts` can `import { STAGE_NODE_IDS, pipelineNodeIds } from '@/machines/pipelinePage'`.
- Plan 09-07 Test 4 (`pipeline-ecs-churn.spec.ts`) still owns the DOM-level/real-SSE-removal proof of the same Done Criterion — this plan's machine test is not a substitute for it, per the plan's own success criteria.
- No blockers for remaining Wave 2 plans in this phase.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

All created files and commit hashes verified present:
- FOUND: ui_service/src/machines/pipelinePage.ts
- FOUND: ui_service/src/machines/__tests__/pipelinePage.test.ts
- FOUND: commit 57c60ea
- FOUND: commit dc0a7cb
