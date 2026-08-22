---
spike: 002
name: ecs-xstate-coexistence
type: standard
validates: "Given the existing locked XState v5 page machines (nexusApp, pipelinePage), when an ECS world runs alongside for entity-level state, then the two compose without duplicated source-of-truth or ownership conflicts"
verdict: PARTIAL
related: [001-ecs-react-flow-render]
tags: [ecs, xstate, architecture, miniplex]
---

# Spike 002: ECS + XState Coexistence

## What This Validates

Given the production `pipelinePageMachine` (`ui_service/src/machines/pipelinePage.ts`, a locked
Phase 6/8 architecture decision — parallel regions, `pipeline: PipelineState` replaced wholesale
on every `SSE_MESSAGE`, a `selection` region tracking `selectedNodeId`), when an ECS world is
layered underneath to hold per-entity rendering state, does the split ownership (XState owns
flow/selection, ECS owns entities) stay clean, or do the two fight over the same facts?

This is a follow-up to spike 001, which invalidated a naive fully-ECS-controlled React Flow
render and validated a buffered pattern (RF owns local node state, ECS patches it). Spike 002
assumes that buffered pattern and asks the architecture question one level up.

## Research

Read the real machine (`ui_service/src/machines/pipelinePage.ts`) before building anything:

- `pipeline: PipelineState | null` is a **single blob**, replaced wholesale by `assign()` on every
  `SSE_MESSAGE` — not merged field-by-field.
- The `selection` region independently owns `selectedNodeId`/`selectedModuleId`.
- The `reviewPanel` region is pure approval flow-control (closed → loading → open →
  approving/rejecting → error) — unrelated to entity rendering, so this spike's stand-in machine
  omits it and only rebuilds `connection` + `selection` faithfully.
- Phase 8 D-04 ("the graph is the notification") means modules genuinely appear/disappear from
  the live pipeline snapshot as their lifecycle changes — entity churn is not an edge case here,
  it's the normal operating mode.

**Chosen approach:** ECS is not a replacement for `pipeline` — it's a derived, rendering-focused
mirror. A `syncFromPipeline()` system runs every time `state.context.pipeline` changes (i.e. on
every `SSE_MESSAGE`), diffing the incoming node list against the ECS world:
- entities in the snapshot but not in the world → added
- entities in the world but not in the snapshot → removed
- entities in both → only **mirrored** fields (`label`, `status`) are patched

Alongside the mirrored fields, entities also carry **ECS-only** components that XState never
sees: `hovered` (mouse hover) and `dragCount` (drag interactions). These represent exactly the
kind of transient, per-object UI state that doesn't belong in serializable app context but is
natural as an ECS component — the sync system's contract is that it must never touch them.

## How to Run

```bash
cd .planning/spikes/002-ecs-xstate-coexistence
npm install
npm run dev                        # http://localhost:5302 — manual/visual verification
node verify.mjs                    # automated: hover survival, drag-while-churn, stale-selection A/B
node verify-hover-followup.mjs     # follow-up probe for the hover-loss finding below
```

The page has a "guard stale selection" checkbox (toggles the `clearSelectionIfMissing` XState
action on/off) and a churn-interval selector. A sync log panel shows every ECS add/remove event
in real time, and `#selected-id` shows XState's live `selectedNodeId`.

## What to Expect

- Hovering a node should visibly ring it in pink; that should **not** flicker while unrelated
  nodes' status colors change from the simulated SSE stream.
- Selecting a node (click) marks it "SELECTED (xstate)"; with the guard checkbox on, selecting a
  node that then disappears from the live graph should auto-clear back to "none". With the guard
  off, the selection can go stale.

## Observability

- On-page sync log (`#sync-log`) — every entity add/remove, driven directly by the diff in
  `syncFromPipeline()`
- `#selected-id` — live readout of XState's `context.selectedNodeId`
- Per-node `dragCount` and hover-state label rendered in the node itself
- `verify.mjs` drives real interactions (click, hover, drag) via Playwright and reads these DOM
  signals directly — no manual eyeballing required for the pass/fail claims below

## Investigation Trail

1. **Built the stand-in machine first, from the real source** (not from imagination) — this
   caught early that `pipeline` is a full-replace blob, which shaped the sync system's diff
   design (compare snapshot vs. world by id, not by deep-equality of the blob).
2. **Hover-survives-sync test:** hovered `orchestrator`, waited 2s (~3 churn ticks at 600ms
   stress interval), checked whether the DOM still showed `hovered (ecs-only)`. Result:
   **it didn't — `hoveredAfter: false`.** Surprising, since the sync system's code comment
   explicitly says it patches only mirrored fields.
3. **Follow-up (`verify-hover-followup.mjs`):** read the sync log directly instead of inferring.
   It showed:
   ```
   sync: adding orchestrator (new in SSE snapshot)
   sync: removing orchestrator (dropped from SSE snapshot)
   sync: adding orchestrator (new in SSE snapshot)
   ```
   Root cause confirmed: the entity was removed and re-added within the 2s window (each node has
   an independent 15% drop chance per tick in this synthetic churn — over 3 ticks that's
   `1 - 0.85^3 ≈ 39%` odds for any given node). A re-add creates a **brand-new entity object**
   with ECS-only fields at their defaults (`hovered: false`). The "only patch mirrored fields"
   guarantee only holds for an entity that persists continuously — it does **not** protect
   against transient absence, because transient absence and genuine removal look identical to a
   presence-diff sync system.
4. **Drag-while-churning test:** dragged `dashboard` for 1.5s (spanning 2 churn ticks affecting
   other nodes) — position tracked correctly, `dragCount` incremented, node survived. No conflict
   observed here; this confirms spike 001's buffered pattern (which already excludes the
   currently-dragged node from external patches) composes fine with the sync system's add/remove
   diffing, as long as the dragged node itself isn't the one being removed mid-drag (not tested —
   noted as an open question below).
5. **The core coexistence test — stale selection, A/B:**
   - **`guardStaleSelection: false`:** selected `orchestrator`, it was dropped from the snapshot
     at churn tick 9, and `selectedIdAfterDrop` remained `"orchestrator"` — **a dangling
     reference**. XState's selection region has no way to know the entity it points at no longer
     exists; nothing in the ECS layer notifies it back. In a real UI this means a review
     panel/highlight could stay open for a module that no longer exists in the graph.
   - **`guardStaleSelection: true`:** same scenario, entity dropped at tick 2, and
     `selectedIdAfterDrop` correctly became `"none"` — because the `clearSelectionIfMissing`
     action re-checks `context.selectedNodeId` against the incoming snapshot on every
     `SSE_MESSAGE`, in the same action list as `updatePipeline`.
   - This confirms the central hypothesis of this spike: **XState and ECS do NOT compose for
     free.** Two independent state owners over overlapping identity (an entity id known to both)
     will drift unless one explicitly watches the other. The fix here is cheap (one extra action
     in the existing `SSE_MESSAGE` handler) *because* XState already receives the full snapshot
     that the ECS sync system also consumes — the guard is written against the same data the sync
     diff uses, not against ECS state directly, so there's no new dependency from XState to ECS.

## Results

**Verdict: PARTIAL.**

- **Coexistence works, but only with an explicit ownership contract, not for free.** ECS and
  XState can cleanly split responsibility (XState: flow/selection/connection; ECS: per-entity
  render state) as long as:
  1. XState remains the single source of truth for *which entities exist* (the snapshot) — ECS
     never adds/removes entities except in reaction to that snapshot.
  2. Any XState state that references an entity by id (like `selectedNodeId`) must be
     re-validated against every new snapshot, in the same transition that would trigger ECS to
     remove that entity. This is not automatic — it must be written by hand, once, per
     cross-referencing field.
  3. ECS-only component data (hover, drag count, or any other transient/local UI state) is only
     as durable as entity identity. If the upstream snapshot's presence/absence is noisy or
     flickery (not necessarily true in production, but true in this synthetic stress test),
     that transient state is silently lost on every remove+re-add cycle. This wasn't anticipated
     going in — the sync system's own contract ("only patch mirrored fields") holds correctly,
     but doesn't cover the remove/re-add case, which is a different failure mode than the one it
     was written to prevent.
- **Requirement added to MANIFEST.md:** if a real implementation wants ECS-only UI state to
  survive brief entity absence (vs. genuine removal), the sync system needs identity
  reconciliation more forgiving than raw per-tick presence — e.g. a short grace/debounce window
  before treating a missing id as removed, or preserving ECS-only components keyed by id across a
  remove/re-add pair instead of discarding them with the old entity object.
- **Open question, not tested:** what happens if the currently-dragged node is the one removed
  mid-drag? Spike 001's buffered pattern protects position during drag by skipping patches to the
  dragged id, but an outright removal (not a patch) wasn't exercised here. Worth a quick check
  before this pattern is used for real, but not blocking for spikes 003/004.
- **Impact on remaining spikes:** Spike 004 (systems as canvas behaviors) should build any
  "entity disappears" behavior (fade-out animation, etc.) as a system that reacts to the
  `clearSelectionIfMissing`-style guard pattern, not assume ECS alone can detect and react to
  removal safely.
