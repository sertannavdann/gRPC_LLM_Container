---
phase: 09-ecs-context-canvas
plan: 03
subsystem: ecs
tags: [miniplex, vitest, ecs, canonical-verbalizer, dirty-tracker, typescript]

requires: ["09-01"]
provides:
  - ui_service/src/ecs/world.ts — createPipelineWorld(), canvasWorld singleton, touch()/subscribeWorld()/getWorldVersion() reactivity bridge
  - ui_service/src/ecs/dirty.ts — createDirtyTracker() with delta version counter
  - ui_service/src/ecs/verbalize.ts — canonicalize()/toCompactDsl()/toDelta()
  - Two green unit suites proving spike 005b (canonical stability) and spike 006 (delta mirror-reconstruction) claims
affects: ["09-ecs-context-canvas plans 04-10"]

tech-stack:
  added: []
  patterns:
    - "add()/removeById()/mutate() are the ONLY choke points into the miniplex World — callers never touch world.add/world.remove directly"
    - "canonicalize() always returns a new sorted copy — never sort in place, never rely on insertion or numeric-eid order"
    - "touch()/subscribeWorld()/getWorldVersion() is a module-global reactivity bridge — required because neither miniplex nor miniplex-react fires on component-value mutation"

key-files:
  created:
    - ui_service/src/ecs/dirty.ts
    - ui_service/src/ecs/world.ts
    - ui_service/src/ecs/verbalize.ts
    - ui_service/src/ecs/__tests__/verbalize.test.ts
    - ui_service/src/ecs/__tests__/dirty.test.ts
  modified: []

key-decisions:
  - "toDelta() takes (dirty, removedIds, viewOf, version) as explicit params rather than closing over a tracker instance, matching the plan's declared export signature exactly"
  - "Removed the duplicate 'pipeline_state — line format' string from verbalize.ts's file-header comment (kept only in toCompactDsl's emitted header line) to satisfy the exact grep-count-1 acceptance criterion"

patterns-established:
  - "Every ecs/*.ts file (including test files under __tests__/) is exempt from 'use client' — only source modules need it; tests do not import client-only APIs directly, but world.ts/dirty.ts/verbalize.ts all carry it per plan"

requirements-completed: [D9-01, D9-03, D9-06, D9-07, D9-14, VAL-W0-VERBALIZE, VAL-W0-DIRTY]

duration: 35min
completed: 2026-09-16
---

# Phase 9 Plan 03: ECS Substrate Core — World, Dirty Tracker, Verbalizer Summary

**Ported the miniplex world (single instance, three choke points), the ~20-line dirty tracker, and the canonical c_state/delta verbalizer from spikes 005b/006/007 verbatim, plus two unit suites proving byte-stable canonical text and exact delta mirror-reconstruction across a deterministic 40-tick churn session.**

## Performance

- **Duration:** ~35 min
- **Tasks:** 3 (all auto)
- **Files created:** 5

## Accomplishments

- `ui_service/src/ecs/dirty.ts`: `createDirtyTracker()` returns `{ dirty, removedIds, version(), markDirty, markRemoved, clearSinceLastInvocation() }`. The delta version counter lives here (not XState context) per CONTEXT.md's Claude's-Discretion note.
- `ui_service/src/ecs/world.ts`: module-level `touch()`/`subscribeWorld()`/`getWorldVersion()` reactivity bridge ported verbatim from the skill blueprint; `createPipelineWorld()` factory wrapping one `new World<EntityRecord>()`, a `byId` map, and a `createDirtyTracker()` instance behind three choke points — `add()`, `removeById()`, `mutate()` — plus `views()`/`viewOf()` projections that strip `x`/`y` and copy `creds`/`flags` arrays so callers never share references with live entities. Exports `canvasWorld` as the module-level singleton.
- `ui_service/src/ecs/verbalize.ts`: `canonicalize()` (stable sorted copy by logical string id), `toCompactDsl()` (grouped-by-kind DSL matching the plan-01 grammar exactly, rounded-integer latency), `toDelta()` (the "unchanged entities omitted" delta header + removed-ids line + trimmed compact-DSL body, dropping the verbalizer's own header).
- Two unit suites: `verbalize.test.ts` (5 tests: insertion-order permutation stability, remove/re-add churn stability, ascending group/id ordering, optional-segment omission, drag-does-not-change-c_state) and `dirty.test.ts` (3 tests: mirror correctness at every invocation across a seeded 40-tick churn script with 26 entities, plus the two markDirty/markRemoved Set-invariant assertions).

## Task Commits

1. **Task 1: Dirty tracker + miniplex world with touch() bridge** — `05ad099` (feat)
2. **Task 2: Canonical verbalizer** — `4d201e4` (feat)
3. **Task 3: Unit suites** — `bb0cd4e` (test)

**Plan metadata:** committed alongside this SUMMARY (worktree mode — orchestrator handles final STATE.md/ROADMAP.md updates after wave completes).

## Exported Signatures (for plans 04-10, so they don't need to re-read source)

```ts
// ui_service/src/ecs/dirty.ts
export interface DirtyTracker {
  dirty: Set<string>;
  removedIds: Set<string>;
  version: () => number;
  markDirty: (id: string) => void;
  markRemoved: (id: string) => void;
  clearSinceLastInvocation: () => number;
}
export function createDirtyTracker(): DirtyTracker;

// ui_service/src/ecs/world.ts
export function touch(): void;
export function subscribeWorld(listener: () => void): () => void;
export function getWorldVersion(): number;
export function createPipelineWorld(): {
  world: World<EntityRecord>;
  byId: Map<string, EntityRecord>;
  tracker: DirtyTracker;
  add(rec: EntityRecord): EntityRecord;
  removeById(id: string): void;
  mutate(id: string, patch: Partial<EntityRecord>): void;
  views(): CanvasView[];
  viewOf(id: string): CanvasView | null;
  entityCount(): number;
};
export const canvasWorld: ReturnType<typeof createPipelineWorld>;

// ui_service/src/ecs/verbalize.ts
export function canonicalize<T extends { id: string }>(views: T[]): T[];
export function toCompactDsl(views: CanvasView[]): string;
export interface DeltaResult { text: string; changed: CanvasView[]; removed: string[]; }
export function toDelta(
  dirty: Set<string>,
  removedIds: Set<string>,
  viewOf: (id: string) => CanvasView | null,
  version: number
): DeltaResult;
```

**Choke-point contract (T-09-09, enforced by plans 04/05):** `sync.ts` and `mediation.ts` must call `add()`/`removeById()`/`mutate()` on a `createPipelineWorld()` (or the `canvasWorld` singleton) instance — never `world.add`/`world.remove` directly, or dirty tracking silently loses events. The invariant `grep -rn "new World" ui_service/src --include="*.ts" | wc -l` returning exactly `1` holds after this plan and must continue to hold.

## Deviations from Plan

**1. [Rule 1 - minor grammar-comment duplication]** The plan's `<action>` prose for Task 2 quoted the full grammar header string in the file's doc comment, in addition to it appearing (correctly) in `toCompactDsl()`'s emitted header line. This produced a grep count of 2 against the acceptance criterion `grep -c "pipeline_state — line format" ... returns 1`. Fixed by replacing the doc-comment's literal restatement with a pointer ("See the header line emitted by toCompactDsl() below") — no behavior change, purely a doc-comment de-duplication. Files: `ui_service/src/ecs/verbalize.ts`. Commit: `4d201e4`.

No other deviations — plan executed as written, including the mandatory reactivity-bridge boilerplate and the choke-point discipline.

## Issues Encountered

- Worktree base commit did not match the wave-2 expected base (`c28fb9e8...`) at agent startup — corrected via `git reset --hard c28fb9e8d4127cd6250094526e04ababf85e3f05` per the `<worktree_branch_check>` protocol before any plan work began (working tree was clean, so nothing was lost).
- `ui_service/node_modules` was absent in the fresh worktree (as expected per plan instructions); ran `npm install --no-fund --no-audit` inside `ui_service/` before any verification. `ui_service/tsconfig.tsbuildinfo` was touched by each `tsc --noEmit` verification run; reverted via `git checkout -- ui_service/tsconfig.tsbuildinfo` before each commit since it is an unrelated tracked build artifact.

## User Setup Required

None — no external service configuration required; all dependencies (`miniplex`, `vitest`) were already installed/approved in plan 01.

## Next Phase Readiness

- `ui_service/src/ecs/world.ts`, `dirty.ts`, and `verbalize.ts` are ready for plan 04 (`sync.ts` — the SSE-to-world sync system) and plan 05 (`mediation.ts`/`history.ts`) to import. Both downstream plans MUST route all entity mutations through `add()`/`removeById()`/`mutate()`.
- `npm run test` (`ui_service`) runs all 3 ECS suites (`types.test.ts`, `verbalize.test.ts`, `dirty.test.ts`) — 13 assertions, ~100ms total, well under the 5-second budget.
- No blockers for wave 2+ plans in this phase.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

- FOUND: ui_service/src/ecs/dirty.ts
- FOUND: ui_service/src/ecs/world.ts
- FOUND: ui_service/src/ecs/verbalize.ts
- FOUND: ui_service/src/ecs/__tests__/verbalize.test.ts
- FOUND: ui_service/src/ecs/__tests__/dirty.test.ts
- FOUND: commit 05ad099
- FOUND: commit 4d201e4
- FOUND: commit bb0cd4e
