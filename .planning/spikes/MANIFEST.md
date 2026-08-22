# Spike Manifest

## Idea (Session 2 — 2026-08-23, context-substrate reframing)

Revisit the ECS spikes through two papers: *A Survey of Context Engineering for LLMs*
(context as `C = A(c1..cn)` with `c_state` assembled from world state; structured beats
prose; deltas/compression beat full dumps; snapshot/restore as a core context-manager
capability) and *LLMs as Software Components* (analyze per LLM component: Prompt State =
Program, Frequency = Iterative, Output Consumer = Program with approval gates as the
Revision mechanism). Under this lens the ECS world is not just a UI state store — it is a
**tri-consumer substrate**: (1) React Flow renders it for the human, (2) XState governs
flow control, (3) a context assembler serializes/diffs it into LLM context, and validated
LLM output mutates it back. Spikes 003a/b compared the libraries only as UI stores; the
serialization/snapshot/delta criteria were never tested. User's call: bitECS is the
presumptive winner under the new criteria — spikes 005/006 validate or invalidate that
with miniplex as control; 007/008 build the write path and replay on the winner.

## Idea (Session 1)

Explore an Entity Component System (ECS) — Bevy-style — as the state model for NEXUS's
interactive "human machine interface" builder: the pipeline/module canvas where live
services, modules, and build stages are visualized and manipulated (React Flow graph on
`ui_service/src/app/pipeline/page.tsx`). The goal is to track stateful objects (nodes,
connections, module blueprints, live status) as ECS entities/components instead of ad-hoc
React state, and use ECS "systems" to implement interactive canvas behaviors (drag, connect,
validate, animate). This must coexist with — not replace — the already-locked XState v5
page-state architecture from Phase 6 (06-CONTEXT.md) and the SSE-driven pipeline stream
(`dashboard_service/pipeline_stream.py`).

## Requirements

- Frontend-only concern: ECS models entity/component-level state (nodes, wires, live status)
  inside the existing Next.js/React `ui_service`, not a backend data model.
- Must coexist with locked XState v5 page machines (nexusApp, pipelinePage) — ECS does not
  replace page-level flow control, only entity/component state within a page.
- Must render through the existing React Flow v12 canvas without fighting React's
  reconciliation loop.
- Must be able to hydrate from the SSE pipeline-state stream (`/stream/pipeline-state`)
  without requiring a full world re-init on every update.
- **ECS mutations must never be surfaced to React Flow as a freshly-derived `nodes` array.**
  (Spike 001) A naive "rebuild `nodes` from `world.entities.map()` on every ECS touch" pattern
  breaks React Flow's rendering entirely (blank canvas) under both stress and realistic load,
  independent of mutation rate — likely a remount/re-measure feedback loop. React Flow must own
  its local node state (`useNodesState`); ECS patches non-positional fields into it by id;
  position writes back to ECS on drag-stop only.
- **XState must remain the single source of truth for entity existence; ECS never adds/removes
  entities except in direct reaction to an XState-owned snapshot.** (Spike 002) Any XState state
  that references an entity by id (e.g. `selectedNodeId`) must be re-validated against every new
  snapshot in the same transition — this doesn't happen automatically and must be hand-written
  per cross-referencing field (see `clearSelectionIfMissing` pattern). Without it, XState state
  can dangle after ECS removes the entity it points to.
- **ECS-only component data (hover, drag state, or other transient UI-only fields) survives only
  as long as the entity is never removed and re-added.** (Spike 002) A sync system that diffs
  "entity in latest snapshot?" to decide add/remove cannot distinguish transient absence from
  genuine removal — a remove+re-add cycle silently discards all ECS-only fields on that entity,
  even though the mirrored fields it's supposed to protect are preserved correctly. If this needs
  to survive brief flicker, the sync system needs debounced/grace-period removal or must carry
  ECS-only components across a remove/re-add pair by id.
- **Use miniplex, not bitECS.** (Spike 003a/003b) bitECS's SoA design pays off at
  thousands-of-entities, numeric-heavy, per-frame-loop scale — none of which describes the
  pipeline canvas (dozens of entities, string-heavy labels/credential lists, no hot simulation
  loop). miniplex won on TypeScript ergonomics (full entity-level type safety vs. bitECS's
  untyped component-presence gap), non-numeric data handling (native vs. hand-rolled parallel
  arrays), and entity hygiene (automatic vs. manual cleanup on remove/recycle). bitECS's
  documented `set()` helper is also a silent no-op without a separately-registered `onSet`
  observer — an easy, undetected footgun.
- **ECS belongs at the entity-collection layer only, not at the per-interaction-behavior layer.**
  (Spike 004) A stateless derivation triggered by a UI event (e.g. highlight-on-hover) built as
  an ECS "system" produced identical correctness and identical measured performance (465 node
  renders, ~430ms for a 10x stress sweep, both implementations) to a plain pure function in
  NEXUS's existing `resolveLifecycle`-style pattern — but took 3x more code (54 vs 17 lines) to
  do it. Canvas behaviors that only derive a value from already-known data (validation,
  highlighting, layout hints) should stay as plain functions. Only behaviors that need to
  read/write the live, SSE-churning entity collection itself belong in ECS.

## Overall Recommendation

If NEXUS pursues an ECS-backed pipeline canvas, scope it narrowly: miniplex (not bitECS) as the
entity store for the live SSE-driven service/module graph, using the buffered React Flow pattern
(spike 001) with XState remaining the source of truth for entity existence and any
XState-owned state that cross-references an entity id (spike 002). Do not route stateless
per-interaction behaviors (validation, highlighting, layout) through ECS systems (spike 004) —
keep those as plain derivation functions, matching the codebase's existing convention.

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | ecs-react-flow-render | standard | ECS-driven React Flow rendering stays stable under SSE-driven updates | ⚠ PARTIAL | ecs, react-flow, rendering |
| 002 | ecs-xstate-coexistence | standard | ECS world composes with existing XState v5 page machines without ownership conflicts | ⚠ PARTIAL | ecs, xstate, architecture |
| 003a | ecs-lib-miniplex | comparison | miniplex ergonomics/TS typing/React integration for this use case | ✓ WINNER | ecs, miniplex, comparison |
| 003b | ecs-lib-bitecs | comparison | bitECS ergonomics/TS typing/React integration for this use case | ✗ INVALIDATED | ecs, bitecs, comparison |
| 004 | ecs-systems-as-canvas-behaviors | standard | ECS systems reduce boilerplate vs current ad-hoc node/panel code | ✗ INVALIDATED | ecs, systems, canvas |
| 005a | world-snapshot-bitecs | comparison | Given the pipeline world in bitECS (str()-branded strings — no interning needed), when serialized to a canonical structured c_state + binary snapshot, then it beats miniplex on the context-substrate criteria | ✗ INVALIDATED | ecs, bitecs, serialization, context-engineering |
| 005b | world-snapshot-miniplex | comparison | Given the same world in miniplex with hand-rolled canonical JSON, when measured on the same criteria, then compare head-to-head | ✓ WINNER | ecs, miniplex, serialization, context-engineering |
| 006 | delta-context-streaming | standard | Given an SSE-churning world and iterative LLM invocations, when invocation n receives only entities changed since n−1 (bitECS ObserverSerializer vs hand-rolled dirty tracking), then deltas apply correctly and cut token cost vs full snapshots | ○ PENDING | ecs, deltas, context-engineering |
| 007 | llm-writes-world | standard | Given schema-validated mutation ops from an LLM component, when applied through a single mediation function alongside SSE sync, then staged/live state coexist and the 002 ownership contract survives two writers | ○ PENDING | ecs, llm-output, approval-gates |
| 008 | snapshot-replay-and-rewind | standard | Given a snapshot ring buffer + delta log, when an approval gate rejects, then the world rewinds to pre-mutation state and a session replays deterministically | ○ PENDING | ecs, snapshots, replay |

**Note on 003a/003b:** the miniplex verdict stands for the *UI-store* criteria it tested.
Spikes 005a/b re-open the library question under *context-substrate* criteria
(serialization, determinism, snapshot cost, delta streams) that 003 never measured.
