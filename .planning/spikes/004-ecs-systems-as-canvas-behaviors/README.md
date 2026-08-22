---
spike: 004
name: ecs-systems-as-canvas-behaviors
type: standard
validates: "Given the ECS systems pattern, when applied to interactive canvas behaviors (drag/connect/validate), then it measurably reduces boilerplate vs the current ad-hoc StageNode/ModuleNode/NodeDetailPanel code"
verdict: INVALIDATED
related: [001-ecs-react-flow-render, 003a-ecs-lib-miniplex]
tags: [ecs, systems, canvas]
---

# Spike 004: ECS Systems vs Ad-hoc Canvas Behaviors

## What This Validates

Does wrapping a cross-entity canvas behavior (hover a node → highlight it and its graph
neighbors, dim everything else) in an ECS "system" measurably reduce code vs. the plain-React
pattern NEXUS's actual pipeline components already use?

## Research

Read the real, current code first, not a hypothetical:

- `ui_service/src/components/pipeline/ModuleNode.tsx` — `resolveLifecycle(d: ModuleNodeData):
  ModuleLifecycle` is a **pure function deriving discrete state from a data object**, called by
  the component to pick a render branch. This is structurally already what an ECS "system" would
  be doing (read component-shaped data, derive a value) — just without a `World` object wrapping
  it.
- `ui_service/src/app/pipeline/page.tsx` — no existing hover/highlight-neighbors behavior exists
  in the codebase today, so this spike had to build a fair equivalent in both styles rather than
  compare against something already shipped. Chose "highlight hovered node + its graph
  neighbors" because it's a genuine **cross-entity** behavior (needs the whole edge list, not
  just one node's own props) — unlike `resolveLifecycle`, which only reads its own entity's data.
  This is the more favorable case for ECS to prove its worth in, since single-entity derivations
  are already well served by the existing pattern.

**Chosen approach:** implement the identical behavior twice, side by side, against the identical
static topology and the identical buffered-React-Flow-patch pattern validated in spike 001:
- **`ecsImpl.ts`** — a miniplex `World`, a `touch()`/`subscribeWorld()` change-notification
  bridge (same as spikes 001/002), and `highlightSystem(hoveredId)` that iterates
  `world.entities` and sets a `highlighted` component.
- **`adhocImpl.ts`** — one pure function, `computeHighlighted(hoveredId): Set<string>`, in the
  same style as `resolveLifecycle`. No world, no bridge, no system — just a function and
  `useMemo`.

## How to Run

```bash
cd .planning/spikes/004-ecs-systems-as-canvas-behaviors
npm install
npm run dev          # http://localhost:5304 — toggle ecs-system / adhoc-react, hover nodes, click "Run stress test"
node verify.mjs       # automated: correctness check + 10x full-sweep stress test, both impls
```

## What to Expect

Hovering "Orchestrator" should highlight it plus Dashboard and Sandbox (its declared
connections), dimming the four module nodes. Both implementations should look and behave
identically — that's the point of the comparison.

## Observability

- Per-node render counter (same instrumentation as spikes 001/002)
- `#render-sum` — live total across all nodes
- `#stress-elapsed` — wall-clock time for a 10x full-sweep hover stress test
- `verify.mjs` drives both implementations through the identical stress test and diffs the
  results directly — no eyeballing required

## Investigation Trail

1. Built `ecsImpl.ts` and `adhocImpl.ts` to produce **identical output** for identical input
   (same `Set<string>` of highlighted ids for a given hovered id), verified by unit-level
   reasoning before wiring up the UI: `highlightSystem` sets `entity.highlighted` from the same
   neighbor-computation logic as `computeHighlighted`.
2. Wired both into the buffered-React-Flow-patch pattern from spike 001, unchanged — the ECS
   version patches from `world.entities` on `touch()`, the ad-hoc version patches from
   `useMemo(computeHighlighted, [hoveredId])` on a `useEffect`. Same shape, same cost, by
   construction — not a coincidence, but exactly what should be expected: the buffered-render
   problem spike 001 solved is orthogonal to where the "highlighted" value comes from.
3. **Correctness check (`verify.mjs`):** hovered "orchestrator" in both implementations —
   identical highlight sets in both (`orchestrator`, `dashboard`, `sandbox` lit; all four
   `module-*` dimmed). No divergence.
4. **Stress test (`verify.mjs`):** 10 full sweeps across all 7 nodes (hover in, hover out, ×7,
   ×10 = 70 hover-in events), measuring total render count summed across every node and wall-clock
   time. Result:
   ```
   ecs-system:   total node renders: 465   stress elapsed: 430ms
   adhoc-react:  total node renders: 465   stress elapsed: 431ms
   ```
   **Identical to within measurement noise.** No performance advantage either direction.
5. **LOC comparison** — the only place a difference showed up, and it went the opposite direction
   from the spike's premise:
   ```
   ecsImpl.ts:   54 lines  (World setup, touch()/subscribeWorld() bridge, byId(), the system)
   adhocImpl.ts: 17 lines  (one pure function)
   ```
   The canvas-wiring code that consumes each (`EcsCanvas`/`AdhocCanvas` in `App.tsx`) came out to
   **the same 32 lines each** — because that code is entirely the buffered-RF-patch pattern from
   spike 001, which doesn't care what produces the value it's patching in.

## Results

**Verdict: INVALIDATED.** For this class of behavior (a stateless derivation computed from a
static or slowly-changing relationship graph, triggered by a UI event), wrapping it in an ECS
"system" did not reduce boilerplate — it added roughly 3x more code (54 vs 17 lines) for
identical correctness and identical measured performance. The reason: NEXUS's existing pattern
(`resolveLifecycle`-style pure functions called from `useMemo`) **already is** the "read
data, derive a value" discipline that ECS systems are supposed to bring. ECS's system concept
doesn't add anything on top of a pure function; a `World` object and a manual change-notification
bridge are pure overhead when there's no actual entity collection that needs to persist, churn,
or carry extra runtime-only state across renders.

**Where ECS's earlier wins (spikes 001–003) still hold:** those spikes justified ECS specifically
for the **live, churning entity collection problem** — SSE-driven pipeline state that adds/removes
entities over time, carries transient per-entity UI state (hover, drag count) that needs to
survive re-renders, and needs a buffered rendering strategy to stay stable. None of that is
present in this spike's static-topology hover behavior. **The conclusion isn't "ECS is
useless" — it's "ECS earns its keep at the entity-collection layer (spikes 001–003), not at the
per-interaction-behavior layer (this spike).**"

**Requirement added to MANIFEST.md:** canvas behaviors that only need to derive a value from
already-known data (validation rules, highlight-on-hover, layout hints) should stay as plain
functions in the existing `resolveLifecycle` style — do not route them through ECS systems. Only
behaviors that need to read/write the live entity collection itself (the thing spikes 001–003's
buffered sync already manages) belong in ECS.

**Impact:** this closes out the spike set. See `.planning/spikes/MANIFEST.md` Requirements for
the consolidated implementation guidance across all four spikes.
