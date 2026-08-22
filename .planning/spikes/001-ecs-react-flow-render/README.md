---
spike: 001
name: ecs-react-flow-render
type: standard
validates: "Given an ECS world managing pipeline-node entities (position/status/connections), when React Flow renders from ECS component queries under active SSE-driven updates, then rendering stays stable/performant without the ECS mutation loop fighting React's reconciliation"
verdict: PARTIAL
related: [002-ecs-xstate-coexistence]
tags: [ecs, react-flow, rendering, miniplex]
---

# Spike 001: ECS + React Flow Render Sync

## What This Validates

Given an ECS world (miniplex) managing pipeline-node entities with position/status/connections
components, when React Flow renders nodes derived from that world under live status updates
(simulating the `dashboard_service/pipeline_stream.py` SSE stream), does the canvas stay stable
and responsive — including while the user is actively dragging a node?

## Research

- **miniplex** (core): entities are plain JS objects; components are properties on them.
  Confirmed from source docs (`node_modules/miniplex-react/README.md`): miniplex's own React
  bindings (`<Entities>`) only re-render "every time the list of entities represented by the
  given query changes" — i.e. on add/remove, **not** on component-value mutation. There is no
  built-in fine-grained reactivity for mutating `entity.position.x = 5`.
- **bitECS**: SoA/data-oriented, higher raw throughput, more manual typing responsibility —
  evaluated head-to-head in spike 003b, not used here.
- Because of the above, any React integration must supply its own change-notification bridge.
  This spike implements the simplest possible one: a global version counter bumped by a
  `touch()` call after any system mutates the world, exposed to React via
  `useSyncExternalStore`.

**Chosen approach:** custom `touch()` bridge (not `miniplex-react`'s `<Entities>`/`useEntities`,
since those only fire on add/remove) driving two candidate integration patterns with React Flow,
built side-by-side in the same app for a fair comparison:

| Approach | Pattern | Pros | Cons |
|---|---|---|---|
| **Naive** | `nodes` prop rebuilt fresh from `world.entities.map()` on every `touch()`; React Flow fully controlled by ECS | Simplest mental model — ECS is the only source of truth | New array + new node objects on every mutation |
| **Buffered** | React Flow owns local state via `useNodesState`; ECS touches patch only non-positional fields into matching nodes by id; position writes back to ECS only on `onNodeDragStop` | Isolates drag responsiveness from ECS churn | Two sources of truth to keep in sync (mitigated by narrow patch surface) |

## How to Run

```bash
cd .planning/spikes/001-ecs-react-flow-render
npm install
npm run dev            # http://localhost:5301 — manual/visual verification
node verify.mjs         # automated Playwright verification (drag + chaos, both modes)
node verify-realistic.mjs  # naive mode under realistic 2s cadence, no drag
```

The page has a mode toggle (naive / buffered), a chaos-interval selector (2000ms realistic /
400ms stress / 50ms extreme), a live FPS counter, and a "drag-vs-touch conflicts" counter. Each
node shows its own render count and who last touched it (`seed` / `chaos` / `drag`).

## What to Expect

- **Buffered mode:** dragging a node stays smooth; other nodes' status colors update live from
  the simulated SSE ticker; per-node render counts stay low (single digits to tens over a few
  seconds).
- **Naive mode:** intended to demonstrate the "ECS fights React" failure mode.

## Observability

Forensic layer built directly into the UI (no separate export needed — this is a rendering-feel
spike, so on-screen counters are the log):
- Per-node `renders` counter (incremented in the node component body)
- `lastTouchedBy` + `updateCount` per entity (who mutated it and how many times)
- Global `fps` counter (rAF-based)
- `drag-vs-touch conflicts` counter (naive mode: counts how many times the full node array was
  rebuilt while a drag was in progress)
- `verify.mjs` / `verify-realistic.mjs` additionally capture screenshots to `evidence/` and read
  the DOM directly via Playwright for objective, scripted measurement (no eyeballing required)

## Investigation Trail

1. **Built both modes side-by-side** in one app (`App.tsx`) so the comparison is apples-to-apples
   against the same entity set and the same chaos ticker.
2. **First run (naive, 400ms chaos + drag):** `verify.mjs` reported **0 drag-vs-touch conflicts**
   (the counter itself undercounts — see gotcha below) but **4921 renders per node** in roughly
   1 second of test time, and `naive-01-after-drag.png` showed a **completely blank canvas** —
   zero visible nodes, only the zoom controls and HUD.
3. **Surprising:** the canvas was blank in `naive-00-before.png` too — *before* any drag
   happened, after only ~1-2 chaos ticks. That ruled out "the drag caused it" as the
   explanation and pointed at something more fundamental.
4. **Follow-up test with zero interaction** (`verify-realistic.mjs`): naive mode, realistic
   2000ms chaos interval, no drag at all, 5.5s of idle observation. Result: still blank canvas,
   and render count hit **2677 per node** — about 487 renders/sec/node — despite only 2-3 real
   chaos ticks occurring in that window. This proved the blowup is **not proportional to mutation
   rate at all**; it's a self-sustaining loop independent of the chaos ticker.
5. **Root-cause hypothesis** (inferred from behavior, not from reading React Flow's internals):
   passing a brand-new `nodes` array with brand-new node objects on every render breaks React
   Flow's identity-based tracking of "is this a node I've already measured/mounted?". React Flow
   auto-fires internal `dimensions`-type `NodeChange` events when it (re)measures a node it
   doesn't recognize. Since `onNodesChange` in naive mode calls `touch()` again after handling
   *any* change (including dimension changes), this creates a tight feedback loop:
   new-array-reference → RF treats nodes as unmeasured → fires dimension change → `onNodesChange`
   → `touch()` → new-array-reference → repeat. The opacity/mount-in CSS transition never
   settles because the "mount" keeps re-triggering, which is consistent with nodes being present
   in the DOM (readable via `.react-flow__node` text content) but invisible in every screenshot.
6. **Second bug found by accident:** in naive mode's `onNodesChange`, the code looped over
   *every* entity in `next` and set `entity.lastTouchedBy = "drag"` unconditionally — not just
   the entity that actually moved. Evidence: after the realistic-cadence run with **no drag
   input whatsoever**, three nodes still showed `touched: drag`. This is a real, easy-to-hit
   pitfall of the naive pattern: without diffing `changes` precisely against `world.entities`,
   any `NodeChange` event (including RF's own internally-generated ones) gets misattributed to
   user action across the entire entity set.
7. **Buffered mode, same drag+chaos test:** canvas stayed visually correct throughout
   (`buffered-01-after-drag.png` — Orchestrator visibly moved to its dropped position, all 8
   nodes rendered with correct colors/status, edges intact). Render counts were 7–67 per node
   (vs. 4921–2677 in naive mode) — roughly two orders of magnitude lower. `lastTouchedBy` was
   correctly attributed per-node (`chaos` for nodes the ticker actually hit, `drag` only for the
   node actually dragged).
8. **Known gap in buffered mode:** `startChaos(chaosMs, draggingId.current)` reads
   `draggingId.current` once, at effect-setup time (not reactively) — so the "don't touch the
   node being dragged" exclusion is stale for any drag that starts after the effect first runs.
   In practice the per-node patch effect's own `if (n.id === draggingId.current) return n` guard
   (checked live, not stale) still protects the dragged node's *local* buffered state, so this
   didn't cause a visible bug in testing — but it's a landmine for a production implementation:
   exclusion lists derived from refs need to be re-evaluated on every use, not captured once.

## Results

**Verdict: PARTIAL.**

- **Naive/fully-ECS-controlled React Flow rendering is INVALIDATED.** It doesn't just perform
  worse — it visibly breaks (blank canvas) under both stress load and realistic load, and even
  with zero interaction, because of a render feedback loop independent of ECS mutation rate.
  This pattern must not be used.
- **Buffered/patch integration is VALIDATED.** React Flow keeps ownership of its own node state
  (`useNodesState`); ECS `touch()` events patch only non-positional data into matching nodes;
  position writes flow back to ECS on drag-stop only. This stayed visually correct and
  performant (7–67 renders/node vs. thousands) under the same stress test.
- **Impact on remaining spikes:** Spike 002 (ECS/XState coexistence) and Spike 004 (systems as
  canvas behaviors) should assume the buffered pattern as the baseline integration — evaluating
  "does XState fit alongside ECS" or "do systems reduce boilerplate" against the naive pattern
  would be evaluating something already known to be non-viable.
- **Requirement added to MANIFEST.md:** ECS entity mutations must never be surfaced to React
  Flow as a freshly-derived `nodes` array; they must patch an RF-owned local node collection by
  id, with position as a drag-stop-only write-back.
