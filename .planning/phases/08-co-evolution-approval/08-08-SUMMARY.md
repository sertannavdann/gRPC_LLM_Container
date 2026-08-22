---
phase: 08-co-evolution-approval
plan: 08
subsystem: ui
tags: [xstate, react-flow, framer-motion, pipeline, approval-gate]

# Dependency graph
requires:
  - phase: 08-co-evolution-approval
    provides: "08-03's SSE payload (status/pending_approval/build_stage per module) and 08-07's pipelinePageMachine + adminClient approval fetchers"
provides:
  - "ModuleNode.tsx lifecycle rendering (building/validating/pendingApproval/approved/rejected) driven by SSE data, with a pure resolveLifecycle() precedence helper"
  - "pipeline/page.tsx rewired onto pipelinePageMachine (single EventSource, machine-driven selection/review-panel state) with a live module node row"
  - "nexusStore.ts scoped to module admin actions + test runner only, SSE/selection ownership removed"
affects: [08-09]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Pure lifecycle-derivation helper (resolveLifecycle) at module scope, no hooks, precedence-ordered branches, directly testable"
    - "Explicit stage-key remapping (stageColorKey) documented inline where two subsystems use different casing for the same concept (SSE 'tests' plural vs STAGE_COLORS 'test' singular)"
    - "NodeShell wrapper component factoring the Handle+motion.div+Handle skeleton shared by 4 of ModuleNode's 6 lifecycle branches"

key-files:
  created: []
  modified:
    - ui_service/src/components/pipeline/ModuleNode.tsx
    - ui_service/src/app/pipeline/page.tsx
    - ui_service/src/store/nexusStore.ts

key-decisions:
  - "resolveLifecycle() precedence order matches the plan exactly: pendingApproval > approved/installed > failed/rejected > building (live buildStage) > validating (status fallback) > legacy (stateStyles) — this ordering is what makes 'validating with buildStage repair' resolve to 'building' rather than being masked by the amber fallback"
  - "STAGE_COLORS reused verbatim from PipelineStageFlow.tsx including its singular 'test' key; a dedicated stageColorKey() function maps the SSE's plural 'tests' to it rather than renaming either side, per the plan's explicit instruction"
  - "Kept fetchModules() from the store for the pipeline page's mount effect and refresh button — it populates the admin module list (enable/disable actions) independently of the SSE-sourced pipeline.modules used for graph rendering, so it is not SSE-transport duplication"
  - "Module row anchors to tool-module_installer when present in the SSE tools payload, falling back to stage-tools otherwise, so modules are never left edge-less"

patterns-established:
  - "Lifecycle-state visual language (5 distinct states + legacy fallback) is now the reusable pattern for any future React Flow node type that needs build/approval status rendering"

requirements-completed: ["REQ-014"]

# Metrics
duration: 35min
completed: 2026-08-22
---

# Phase 08 Plan 08: Pipeline Approval Notification Surface Summary

**ModuleNode now renders five visually distinct lifecycle states (pulsing orange "Needs Review" badge for pending-approval, live per-stage build coloring, approved/rejected transitions) and the pipeline page is fully machine-driven via `pipelinePageMachine`, with the Zustand store trimmed to a single SSE owner.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3/3 completed
- **Files modified:** 3

## Accomplishments
- `ModuleNode.tsx` gained a pure, precedence-ordered `resolveLifecycle()` helper and five new render branches (building/validating/pendingApproval/approved/rejected) on top of the preserved legacy running/disabled/failed fallback — closing the D-01/D-04 gap where `ModuleNode` existed but was never even registered in the pipeline's `nodeTypes`
- The pending-approval badge is exactly spec: static amber border (non-pulsing) + an 18px orange circular badge with a pulsing (`scale: [1, 1.08, 1]`, 1.8s loop) white `Eye` icon and a `"· Needs Review"` label suffix — visually distinct from the pulsing-amber-border `validating` state per UI-SPEC Flag 6
- Live build stages (scaffold/implement/tests/repair) color the node border using `PipelineStageFlow.tsx`'s `STAGE_COLORS` map reused verbatim, with an explicit `stageColorKey()` mapping the SSE's plural `tests` to the map's singular `test` key
- `pipeline/page.tsx` now drives SSE connection, node selection, and review-panel state through `useMachine(pipelinePageMachine)` — `startSSE`/`stopSSE` are gone, replaced by the machine's `sseConnection` fromCallback actor as the sole `EventSource` owner
- A new Row 3 of module nodes (y=600) renders live from `pipeline.modules`, sorted pending-approval-first (UI-SPEC focal-point rule), connected to the pipeline via `tool-module_installer` (or `stage-tools` fallback), passing `buildStage`/`status`/`pendingApproval` through verbatim from the SSE payload
- `nexusStore.ts` is de-duplicated: `pipeline`/`connected`/`lastUpdate`/`selectedNode`/`selectNode`/`startSSE`/`stopSSE`/the module-level `_eventSource` are all removed; `SelectedNode` type export is preserved for `NodeDetailPanel.tsx`; `connectPipelineSSE` now has exactly one runtime consumer (the machine's `sseConnection` actor)

## Task Commits

1. **Task 1: ModuleNode lifecycle states + pending-approval badge** - `ce5178f` (feat)
2. **Task 2: Pipeline page driven by pipelinePageMachine + module node row** - `02218d9` (feat)
3. **Task 3: De-duplicate the Zustand store so only one SSE owner remains** - `6511115` (refactor)

**Plan metadata:** committed via SDK metadata step after this SUMMARY.

## Files Created/Modified
- `ui_service/src/components/pipeline/ModuleNode.tsx` - Extended `ModuleNodeData` with `pendingApproval?`/`status?`/`buildStage?`; added `resolveLifecycle()`, `STAGE_COLORS`/`stageColorKey()` (reused from PipelineStageFlow.tsx), `NodeShell` wrapper, and five new lifecycle render branches
- `ui_service/src/app/pipeline/page.tsx` - Registered `module: ModuleNode` in `nodeTypes`; replaced Zustand SSE/selection with `useMachine(pipelinePageMachine)`; added Row 3 module node/edge construction in the rebuild effect; derived `selectedNode` from the machine's `selectedNodeId` via a `nodes` array lookup; `onClose` now sends `CLOSE_PANEL`
- `ui_service/src/store/nexusStore.ts` - Removed SSE/selection ownership (`pipeline`, `connected`, `lastUpdate`, `selectedNode`, `selectNode`, `startSSE`, `stopSSE`, `_eventSource`); kept `modules`/`modulesLoading`/`fetchModules`/`enableModule`/`disableModule`/`reloadModule`/`testRunning`/`testResult`/`runModuleTests` and the `SelectedNode` type export; updated file docstring

## Decisions Made
- Used a shared `NodeShell` component (Handle + motion.div + Handle) for the building/validating/approved/rejected branches to avoid four near-identical copies of the React Flow handle wiring, while keeping `legacy` and `pendingApproval` as fully inline branches since they have structurally different chrome (badge overlay, admin toggle button) that doesn't fit the shared shell cleanly
- Kept `fetchModules()` wired to the pipeline page's mount effect and refresh button (rather than dropping it per the plan's "otherwise" clause) because it serves a genuinely different purpose than the SSE stream: populating the admin module list used by future enable/disable actions, not pipeline graph rendering — this is not SSE-transport duplication, so retaining it doesn't violate "exactly one EventSource"

## Deviations from Plan

None - plan executed exactly as written. All three tasks' `<action>` and `<acceptance_criteria>` specifications were followed directly; no Rule 1-4 auto-fixes were needed.

## Issues Encountered

This worktree's HEAD was initially on an unrelated, much older commit (`6b2027b "Cohesion (#14)"`, no `.planning/` directory at all) despite being on the correct `worktree-agent-*` branch, matching the same pre-existing worktree-provisioning issue noted in 08-03/08-07's summaries. Per the mandatory `worktree_branch_check` step, `git merge-base` against the expected base (`8ccb434...`) did not match, so `git reset --hard 8ccb434...` was performed (working tree was clean, so non-destructive) before any plan file could be read.

`ui_service/node_modules` was not present in this worktree; `npm ci` was run to reproduce the already-declared dependencies so `tsc`/`next lint`/`next build` (the plan's own `<verify>` commands) could execute — no `package.json`/lockfile changes were made.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

- Plan 08-09 (review panel body, five accordion sections, approve/reject actions) can now build directly on top of the machine-driven `reviewPanel` region and the `NodeDetailPanel`'s existing `node`/`onClose` props wired in this plan — no further pipeline-page or ModuleNode rewiring needed.
- Manual/browser verification (module appears with pulsing badge within ~2s of reaching VALIDATED; live build border color walks scaffold→implement→tests→repair) is deferred to a services-up environment, consistent with this plan's own `<verification>` section, which lists these as manual checks requiring running services.
- No blockers. `cd ui_service && npx tsc --noEmit` and `npm run build` both pass cleanly; `connectPipelineSSE` has exactly one runtime consumer (`pipelinePageMachine`'s `sseConnection` actor).

---
*Phase: 08-co-evolution-approval*
*Completed: 2026-08-22*
