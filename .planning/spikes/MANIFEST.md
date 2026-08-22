# Spike Manifest

## Idea

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

## Spikes

| # | Name | Type | Validates | Verdict | Tags |
|---|------|------|-----------|---------|------|
| 001 | ecs-react-flow-render | standard | ECS-driven React Flow rendering stays stable under SSE-driven updates | ⚠ PARTIAL | ecs, react-flow, rendering |
| 002 | ecs-xstate-coexistence | standard | ECS world composes with existing XState v5 page machines without ownership conflicts | PENDING | ecs, xstate, architecture |
| 003a | ecs-lib-miniplex | comparison | miniplex ergonomics/TS typing/React integration for this use case | PENDING | ecs, miniplex, comparison |
| 003b | ecs-lib-bitecs | comparison | bitECS ergonomics/TS typing/React integration for this use case | PENDING | ecs, bitecs, comparison |
| 004 | ecs-systems-as-canvas-behaviors | standard | ECS systems reduce boilerplate vs current ad-hoc node/panel code | PENDING | ecs, systems, canvas |
