---
phase: 09-ecs-context-canvas
plan: 08
subsystem: ui
tags: [react-flow, ecs, preview, proposal-overlay, pending-confirmation, playwright]

requires:
  - phase: 09-ecs-context-canvas
    provides: "canvasMediation.proposals/previewViews/approve (plan 04), the buffered React Flow patch pattern and [pipeline]/[version] effects (plan 07)"
provides:
  - "ui_service/src/ecs/preview.ts — proposalAnnotations() pure derivation, createPendingConfirmations() grace registry, pendingConfirmations module singleton"
  - "ui_service/src/components/pipeline/ModuleNode.tsx — violet field/ghost/removal proposal overlay + zinc confirming treatment, layered around the six locked lifecycle renderings without touching them"
  - "ui_service/src/app/pipeline/page.tsx — data.proposal/data.confirming injected through the existing [version] patch effect; ghost nodes appended in the existing [pipeline] ingestion effect"
affects: ["09-09 (approval flow will call pendingConfirmations.mark(id) after an add_module approval)", "09-10"]

tech-stack:
  added: []
  patterns:
    - "Proposal overlay is a pure render-time derivation (proposalAnnotations), never an ECS system — same discipline as resolveLifecycle()"
    - "Existing lifecycle branches extracted verbatim into renderLifecycleContent(); a new ProposalOverlay wrapper component composes around it via CSS outline (never border) so the visual regression lock holds"
    - "Ghost nodes for staged add_module proposals are synthesized directly from canvasMediation.proposals inside the existing ingestion effect (not canvasGraph.ts) — no third effect added"

key-files:
  created:
    - ui_service/src/ecs/preview.ts
    - ui_service/src/ecs/__tests__/preview.test.ts
  modified:
    - ui_service/src/components/pipeline/ModuleNode.tsx
    - ui_service/src/app/pipeline/page.tsx

key-decisions:
  - "Grace period used: 4000ms ([DEFAULT], 2x the 2s SSE tick) — createPendingConfirmations({ graceMs = 4000 })"
  - "Pending-confirmation registry singleton lives in ecs/preview.ts as `export const pendingConfirmations = createPendingConfirmations()` (module-scope singleton, mirrors canvasMediation/canvasWorld) — plan 09's approval flow imports it directly, no prop drilling"
  - "annotationKey(proposalId|kind|deltaLines.join('|')) used for value-comparison in the [version] patch effect so the early-return-identical-reference optimization survives a fresh Map returned every proposalAnnotations() call"
  - "Ghost node label/category come directly from canvasMediation.proposals' add_module op.rec (not from proposalAnnotations(), which intentionally carries no rec fields) — proposalAnnotations() stays a pure id->annotation map"

requirements-completed: [D9-08, D9-11, T-09-03]

duration: 55min
completed: 2026-09-16
---

# Phase 09 Plan 08: Proposal Preview Overlay + Pending-Confirmation Summary

**Staged LLM proposals now render as violet dashed-outline overlays on live module nodes (or a dedicated ghost shell for not-yet-existing entities), and optimistically-approved adds show a distinct zinc "Confirming…" treatment until the next SSE snapshot resolves them or a 4-second grace window expires.**

## Performance

- **Duration:** ~55 min
- **Tasks:** 3 (all `type="auto"`)
- **Files modified:** 2 created, 2 modified

## Accomplishments

- `preview.ts`: `proposalAnnotations()` — a pure `Map<proposalId-scoped proposals> -> Map<entity id, ProposalAnnotation>` derivation covering `set_status`/`set_credentials`/`move` (`kind: 'field'`, one delta line per op in exact UI-SPEC arrow notation), `add_module` (`kind: 'ghost'`), and `remove_module` (`kind: 'removal'`); only `staged` proposals produce annotations. `createPendingConfirmations()` — `mark`/`resolve`/`expired`/`pendingIds`/`clear` grace registry, `[DEFAULT]` 4000ms, exported as a module-scope singleton (`pendingConfirmations`).
- `preview.test.ts`: 11 vitest cases — one-annotation-per-op-kind, no annotation on approved/invalidated proposals, no credential names in delta lines (T-09-06), non-mutation proof, and exact grace-boundary arithmetic (`+4001` expires, `+3999` does not, custom `graceMs` respected).
- `ModuleNode.tsx`: extracted the six locked lifecycle renderings verbatim into `renderLifecycleContent()`, added a `GhostModuleNode` shell for staged `add_module` proposals, and a `ProposalOverlay` wrapper adding the violet corner badge / dashed `outline` (not `border`) / delta lines for `field`, the 50%-opacity + `"· Proposed Removal"` treatment for `removal`, and the zinc dashed + spinning `Loader2` + `"· Confirming…"` treatment when `confirming` is true and no proposal is staged (`proposal` wins precedence, documented inline).
- `page.tsx`: the existing `[version]`-keyed patch effect now also computes `proposalAnnotations(canvasMediation.proposals)` and `pendingConfirmations.pendingIds()` once per run, sets `data.proposal`/`data.confirming` per node, and compares annotations by value (`annotationKey`) to preserve the same-reference optimization. The existing `[pipeline]`-keyed ingestion effect resolves/expires pending confirmations in the same transition as `syncFromPipeline`, and appends ghost nodes (sourced from `canvasMediation.proposals`' `add_module` ops directly, for full `label`/`category`) using the same auto-layout row as real modules. No new `useEffect` was added.

## Task Commits

Each task was committed atomically:

1. **Task 1: preview.ts — pure annotation derivation and the pending-confirmation registry** - `efd7b59` (feat)
2. **Task 2: ModuleNode.tsx — violet proposal overlay and zinc confirming treatment** - `0c8d8bb` (feat)
3. **Task 3: Inject annotations into node data through the existing patch effect** - `a88dd02` (feat)

## Files Created/Modified

- `ui_service/src/ecs/preview.ts` - `ProposalAnnotation` type, `proposalAnnotations()`, `PendingConfirmations`/`createPendingConfirmations()`, `pendingConfirmations` singleton
- `ui_service/src/ecs/__tests__/preview.test.ts` - 11 vitest cases
- `ui_service/src/components/pipeline/ModuleNode.tsx` - `ModuleNodeData.proposal`/`.confirming` optional fields, `renderLifecycleContent()` extraction (unchanged content), `GhostModuleNode`, `ProposalOverlay`, new `Sparkles`/`Loader2` icon imports
- `ui_service/src/app/pipeline/page.tsx` - `annotationKey()` helper, ghost-node synthesis in the ingestion effect, `data.proposal`/`data.confirming` injection + pending resolve/expire in the patch/ingestion effects, new `canvasMediation`/`proposalAnnotations`/`pendingConfirmations` imports

## Decisions Made

- Chose the `preview.ts` module-scope singleton (`pendingConfirmations`) over lifting it into `page.tsx`, matching the existing `canvasMediation`/`canvasWorld` singleton pattern already established in `ecs/` — plan 09's approval flow (`mark(id)` after an `add_module` approval) can import it directly with no prop drilling.
- Ghost-node construction reads `canvasMediation.proposals` directly in `page.tsx` (not `proposalAnnotations()`'s output) because a ghost needs the full `add_module` op's `rec.label`/`rec.category`, which `proposalAnnotations()` deliberately does not carry — keeping `proposalAnnotations()` a pure id-keyed annotation map, not a node-builder.
- `renderLifecycleContent()` extraction (rather than editing each of the six branches in place) was the only way to satisfy "wrap the existing rendering... without touching a single line inside these branches" while still producing a single component export — verified via `git diff` showing `stateStyles`/`STAGE_COLORS` and the branch bodies byte-identical to before.

## Deviations from Plan

None — plan executed as written. The `preview.ts` grace value (4000ms) and the singleton-location choice (in `preview.ts`, not `page.tsx`) were both explicitly left open by the plan for the executor to decide and record here, per its `<output>` directive.

## Issues Encountered

- `ModuleNodeData.state` is typed `'running' | 'disabled' | 'failed'`; the ghost node has no live state yet, so `state: 'disabled'` is used as a type-safe placeholder (never read by `GhostModuleNode`, which renders its own dedicated shell independent of `state`).
- Docker Desktop stack was down at agent start; brought up from the main checkout (`docker compose up -d`, never from the worktree) per the parallel-execution guidance.
- The running `ui_service` container serves the main checkout's image, not this worktree's `page.tsx`/`ModuleNode.tsx` changes — ran the worktree's own `next dev -p 3101` against the shared dashboard (`http://localhost:8001`), matching 09-07's documented pattern.
- Test 4 of `pipeline-ecs-churn.spec.ts` (the probe-module lifecycle test) requires `E2E_MODULES_ROOT` pointed at the main checkout's `modules/` directory (the one actually bind-mounted into the `dashboard` container), not this worktree's own — used `E2E_MODULES_ROOT=/Users/sertanavdan/Documents/Software/AI/gRPC_llm`, exactly as documented in 09-07-SUMMARY.md.

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

- Plan 09's approval flow can call `pendingConfirmations.mark(id)` (imported from `ecs/preview.ts`) immediately after an `add_module` proposal's `approve()` succeeds — the ingestion effect already resolves/expires marked ids on every SSE tick, and the `[version]` patch effect already reflects `confirming` on any node whose id is marked.
- `ModuleNode.tsx`'s `ProposalOverlay`/`GhostModuleNode` are ready for plan 09's `NodeDetailPanel` `canvasOpApproval` review surface — clicking a node with `data.proposal` set already carries `proposalId`/`kind`/`deltaLines` for that panel to render.
- `npm run test` (8 suites, 57 tests), `npx tsc --noEmit`, and `npm run build` all pass clean. `pipeline-ecs-churn.spec.ts` 4/4 non-disruptive tests pass against a live docker-compose dashboard with this plan's page.tsx/ModuleNode.tsx changes.
- No blockers.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

All files verified present; all 3 task commits (`efd7b59`, `0c8d8bb`, `a88dd02`) verified in `git log`.
