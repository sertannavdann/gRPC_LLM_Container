# Spike Wrap-Up Summary

**Dates:** 2026-08-22 (session 1), 2026-09-15 (session 2)
**Spikes processed:** 10 (5 + 5)
**Feature areas:** ECS-Backed Pipeline Canvas; LLM Context Substrate
**Skill output:** `./.claude/skills/spike-findings-grpc-llm/` (local-only — `.claude/` is gitignored)

## Processed Spikes

| # | Name | Type | Verdict | Feature Area |
|---|------|------|---------|--------------|
| 001 | ecs-react-flow-render | standard | ⚠ PARTIAL | ECS-Backed Pipeline Canvas |
| 002 | ecs-xstate-coexistence | standard | ⚠ PARTIAL | ECS-Backed Pipeline Canvas |
| 003a | ecs-lib-miniplex | comparison | ✓ WINNER | ECS-Backed Pipeline Canvas |
| 003b | ecs-lib-bitecs | comparison | ✗ INVALIDATED | ECS-Backed Pipeline Canvas |
| 004 | ecs-systems-as-canvas-behaviors | standard | ✗ INVALIDATED | ECS-Backed Pipeline Canvas |
| 005a | world-snapshot-bitecs | comparison | ✗ INVALIDATED | LLM Context Substrate |
| 005b | world-snapshot-miniplex | comparison | ✓ WINNER | LLM Context Substrate |
| 006 | delta-context-streaming | standard | ✓ VALIDATED | LLM Context Substrate |
| 007 | llm-writes-world | standard | ✓ VALIDATED | LLM Context Substrate |
| 008 | snapshot-replay-and-rewind | standard | ✓ VALIDATED | LLM Context Substrate |

## Key Findings

### Session 1 — ECS as UI store
- Naive ECS→React Flow rendering breaks outright (blank canvas); the buffered pattern is mandatory.
- ECS and XState coexist only with an explicit ownership contract (XState owns existence;
  `clearSelectionIfMissing`).
- miniplex beats bitECS for UI ergonomics; bitECS `set()` is a silent no-op without `onSet`.
- ECS "systems" are the wrong layer for stateless per-interaction behaviors (3× code, 0 benefit).

### Session 2 — ECS as LLM context substrate (context-engineering reframing)
- The bitECS reversal hypothesis was tested on its own best criteria and invalidated twice:
  binary snapshots 40× slower and non-canonical under churn, duplicate entities on same-world
  restore, no win even on numeric-only 50k entities; delta packets opaque with a zero-skip gotcha.
- Token cost is library-independent; format is a 2.9× lever (compact DSL 752 vs pretty JSON 2,175).
- Delta contexts: 49% → 95% savings as world grows, mirror-reconstruction exact; the tracker is
  ~30 lines because the 002 choke-point discipline already exists.
- Single-path mediation with staged proposals + 3-point re-validation survived every two-writer
  race (17/17); optimistic adds need pending-confirmation handling.
- Snapshot ring + event log gives rewind/undo/redo/replay at ~80 LOC and closes the 002
  ECS-only-field gap for rewind scenarios.

**Overall recommendation:** miniplex world as the tri-consumer substrate (React Flow, XState,
context assembler), buffered rendering, canonical verbalizer + delta contexts, one mediation path
for all writers, clear-then-restore history. Planned as Phase 9 (`.planning/phases/09-ecs-context-canvas/`).
