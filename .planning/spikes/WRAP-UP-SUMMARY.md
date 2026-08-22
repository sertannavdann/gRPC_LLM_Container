# Spike Wrap-Up Summary

**Date:** 2026-08-22
**Spikes processed:** 5
**Feature areas:** ECS-Backed Pipeline Canvas
**Skill output:** `./.claude/skills/spike-findings-grpc-llm/`

## Processed Spikes

| # | Name | Type | Verdict | Feature Area |
|---|------|------|---------|--------------|
| 001 | ecs-react-flow-render | standard | ⚠ PARTIAL | ECS-Backed Pipeline Canvas |
| 002 | ecs-xstate-coexistence | standard | ⚠ PARTIAL | ECS-Backed Pipeline Canvas |
| 003a | ecs-lib-miniplex | comparison | ✓ WINNER | ECS-Backed Pipeline Canvas |
| 003b | ecs-lib-bitecs | comparison | ✗ INVALIDATED | ECS-Backed Pipeline Canvas |
| 004 | ecs-systems-as-canvas-behaviors | standard | ✗ INVALIDATED | ECS-Backed Pipeline Canvas |

## Key Findings

- **Naive ECS→React Flow rendering breaks outright** (Spike 001): deriving the `nodes` prop
  fresh from `world.entities.map()` on every mutation produced a blank canvas and
  ~2700–4900 renders/node/sec, independent of mutation rate — even at rest. The buffered
  pattern (React Flow owns local state, ECS patches by id, position writes back on drag-stop)
  stayed correct at 7–67 renders/node under the same stress.
- **ECS and XState coexist only with an explicit ownership contract** (Spike 002): XState owns
  entity existence; any id-referencing XState state (e.g. `selectedNodeId`) dangles after entity
  removal unless re-validated per snapshot (`clearSelectionIfMissing` pattern, A/B-confirmed).
  ECS-only fields (hover, drag count) are silently wiped by a remove+re-add cycle.
- **miniplex beats bitECS for this domain** (Spikes 003a/003b): full entity-level type safety,
  native string-heavy data, automatic entity hygiene. bitECS's `set()` helper is a silent no-op
  without a separately-registered `onSet` observer — wrong data with zero errors.
- **ECS "systems" are the wrong layer for stateless per-interaction behaviors** (Spike 004):
  identical correctness and identical measured performance (465 renders, ~430ms stress sweep)
  vs. a plain `resolveLifecycle`-style pure function — at 3x the code (54 vs 17 lines).

**Overall recommendation:** if pursued, scope ECS narrowly — miniplex as the entity store for
the live SSE-driven graph, buffered React Flow rendering, XState as existence source of truth,
and plain derivation functions for per-interaction behaviors. Full blueprint in
`./.claude/skills/spike-findings-grpc-llm/references/ecs-pipeline-canvas.md`.
