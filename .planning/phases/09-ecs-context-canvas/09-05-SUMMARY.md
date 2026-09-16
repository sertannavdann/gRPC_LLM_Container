---
phase: 09-ecs-context-canvas
plan: 05
subsystem: ui
tags: [miniplex, ecs, history, rewind, redo, undo]

requires:
  - phase: 09-ecs-context-canvas
    provides: "world.ts (createPipelineWorld choke points, touch()), mediation.ts (createMediation, propose/approve/reject), sync.ts (syncRecords) from plans 03/04"
provides:
  - "ui_service/src/ecs/history.ts — createSnapshotRing, createEventLog, restoreSnapshot, replayEvents, createHistory, canvasHistory"
  - "ui_service/src/ecs/__tests__/history.test.ts — automated proof of clear-then-restore anti-duplication, dirty-marking, UI-only field survival, and replay determinism"
affects: ["09-09/09-10 (rewind toast + undo/redo toolbar UI wiring to canvasHistory)"]

tech-stack:
  added: []
  patterns:
    - "Rewind = clear-then-restore over the SAME world object (never in-place) — spike 005a's proven anti-duplication fix"
    - "Redo = event-log replay through the single mediation propose/approve path — no inverse-op machinery"
    - "Checkpointed event log: dropPrefix keeps the log bounded to the ring's capacity horizon so it cannot grow unbounded across a page-lifetime session"

key-files:
  created:
    - ui_service/src/ecs/history.ts
    - ui_service/src/ecs/__tests__/history.test.ts
  modified: []

key-decisions:
  - "EventLog seq is an independent monotonic counter (not events.length), so seq values survive dropPrefix checkpointing without collision"
  - "recordSync's checkpoint threshold is capacity-based (log.lastSeq() - capacity + 1), not tied to ring.size() directly, so the log stays bounded at all ring-fill states including before the ring reaches capacity"
  - "replayEvents imports syncRecords directly from sync.ts (no circular dependency exists — sync.ts never imports history.ts), avoiding an unnecessary binding indirection"

requirements-completed: [D9-12, D9-13, VAL-W0-HISTORY]

duration: 30min
completed: 2026-09-16
---

# Phase 09 Plan 05: History Layer (Snapshot Ring + Event Log + Rewind/Redo) Summary

**Bounded snapshot ring, checkpointed event log, and clear-then-restore rewind/redo composed into a `createHistory()` API that plans 09/10's UI call directly — no inverse-op machinery, no in-place restore.**

## Performance
- **Duration:** ~30 min
- **Tasks:** 2 (both `type="auto"`)
- **Files modified:** 2 created, 0 modified

## Accomplishments
- `history.ts`: ported `createSnapshotRing`/`restoreSnapshot`/`createEventLog`/`replayEvents` from spike 008 verbatim (including comments), with the two mandatory browser adaptations (`TextEncoder` instead of `Buffer.byteLength`, `touch()` call after restore) and the `EntityRecord`-full-record snapshot contract (D9-13).
- `createHistory(w, m, { capacity })` composes `recordSync`, `approveWithHistory`, `rejectWithRewind`, `undo`, `redo`, `canUndo`, `canRedo` — the exact API surface plans 09/10 need.
- `history.test.ts`: 9 tests covering anti-duplication after drift, dirty-marking, UI-only field (`x`/`y`) survival, reject-with-rewind (both the staged and approved branches), replay determinism (byte-identical serialization across two independent worlds), loud replay divergence, ring bounding + log checkpointing, and an undo/redo round trip.
- All acceptance-criteria greps verified directly (`'use client'` header, zero `Buffer.byteLength`, one `TextEncoder`, clear-loop before re-add loop, `touch()` present, `dropPrefix`/checkpoint present).
- `npm run test` (6 suites, 41 tests) and `npx tsc --noEmit` both pass clean.

## Task Commits
1. **Task 1: Snapshot ring, event log, clear-then-restore rewind, replay** — `84010ea` (feat)
2. **Task 2: history.test.ts — rewind determinism and replay equality** — `7d01156` (test, includes a Rule-1 bugfix to the event-log seq counter found while writing the ring-bounding test)

## Files Created/Modified
- `ui_service/src/ecs/history.ts` — `createSnapshotRing`, `restoreSnapshot`, `createEventLog`, `replayEvents`, `createHistory`, `canvasHistory` singleton
- `ui_service/src/ecs/__tests__/history.test.ts` — 9-test suite (`vitest`)

## createHistory API surface (for plans 09/10)

```ts
const h = createHistory(w, m, { capacity = 20 });

h.recordSync(records: EntityRecord[]): void
// Pushes a ring snapshot + logs a 'sync' event; checkpoints the log to the
// ring's capacity horizon. Call this whenever the caller performs a sync
// via sync.ts's syncRecords/syncFromPipeline, in addition to that call.

h.approveWithHistory(pid: string): { ok: boolean; error?: string; label: string }
// Pushes a `pre-approve:${pid}` snapshot BEFORE calling m.approve(pid);
// on success logs an 'approve' event with the proposal's ops.

h.rejectWithRewind(pid: string): { ok: boolean; rewound: boolean }
// staged proposal -> delegates to m.reject(pid), rewound: false (nothing
// applied). approved proposal -> restoreSnapshot from `pre-approve:${pid}`,
// marks it rejected, rewound: true. The `rewound` flag is the UI's signal
// to show the rewind toast.

h.undo(): { ok: boolean; label?: string }
h.redo(): { ok: boolean; label?: string }
// undo restores backward along the ring; redo restores forward, or replays
// the tail of the event log when returning to the newest ring entry.

h.canUndo(): boolean
h.canRedo(): boolean
// Drive the disabled state of the plan-10 toolbar buttons.

h.ring / h.log
// Direct access to the underlying SnapshotRing/EventLog, exposed for
// diagnostics and the ring-bounding test; not required for normal UI use.
```

`canvasHistory = createHistory(canvasWorld, canvasMediation)` is the production singleton plans 09/10 import directly.

## Decisions Made
- `EventLog`'s `seq` field is assigned from an independent `nextSeq` counter, not `events.length` — the array shrinks on `dropPrefix`, and deriving `seq` from its length would cause new events to collide with surviving lower-index events after a checkpoint. Found and fixed while writing the ring-bounding test (see Deviations).
- `recordSync`'s checkpoint call computes `Math.max(0, log.lastSeq() - capacity + 1)` rather than tying the drop threshold to `ring.size()` — this keeps the log bounded to at most `capacity` live events at every point in the ring's fill lifecycle, not only once the ring is full.
- `replayEvents` imports `syncRecords` directly from `sync.ts` rather than using a lazy-bound indirection — `sync.ts` never imports `history.ts`, so there is no circular-import hazard to route around, and the plan's own action text ("sync events call `syncRecords(w, m, payload)`") describes a direct call.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Event-log `seq` collision after checkpoint drop**
- **Found during:** Task 2, writing the ring-bounding + checkpoint test
- **Issue:** `record()` assigned `seq: events.length`. After `dropPrefix` shrank the array, the next `record()` call computed a `seq` from the now-smaller `events.length`, producing duplicate/out-of-order `seq` values across the checkpoint boundary. The ring-bounding test failed with `log.length()` growing past `capacity` because the drop threshold math (originally tied to `ring.size()`) also needed correcting once `seq` was fixed to be trustworthy.
- **Fix:** Added an independent `nextSeq` counter inside `createEventLog()`'s closure, incremented on every `record()` call regardless of prior drops; changed `recordSync`'s checkpoint threshold to `log.lastSeq() - capacity + 1` (added a `lastSeq()` accessor to `EventLog`).
- **Files modified:** `ui_service/src/ecs/history.ts`
- **Commit:** `7d01156`

## User Setup Required
None — no external service configuration required.

## Next Phase Readiness
- `canvasHistory` (and the pure `createHistory` factory for isolated instances) is ready for plan 09/10's rewind-toast and undo/redo toolbar wiring.
- `npm run test` (6 suites, 41 tests) and `npx tsc --noEmit` both pass clean in `ui_service/`.
- No blockers.

---
*Phase: 09-ecs-context-canvas*
*Completed: 2026-09-16*

## Self-Check: PASSED

Both created files verified present (`history.ts`, `history.test.ts`); both task commits (`84010ea`, `7d01156`) verified in `git log`.
