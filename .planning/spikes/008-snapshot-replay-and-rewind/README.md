---
spike: 008
name: snapshot-replay-and-rewind
type: standard
validates: "Given a snapshot ring buffer + event log, when an approval gate rejects (or the user undoes), then the world rewinds to pre-mutation state and a session replays deterministically"
verdict: VALIDATED
related: [005b-world-snapshot-miniplex, 007-llm-writes-world, 002-ecs-xstate-coexistence]
tags: [ecs, snapshots, replay, undo, history]
---

# Spike 008: Snapshot Replay and Rewind

## What This Validates

The survey's snapshot/restore context-manager capability made concrete: a bounded ring
of canonical JSON snapshots (005b's serializer) paired with an append-only semantic
event log (`sync` + `approve` events through the 007 mediation layer). Rewind for
rejected/undone proposals, deterministic session replay, and undo/redo.

## How to Run

```bash
npm install && node run.mjs   # 9-check rig, exits non-zero on failure
```

## Investigation Trail

1. Rewind = **clear-then-restore into the same world** — the only safe mode, per 005a's
   probe where in-place restore over a drifted world duplicated entities. Exact
   pre-proposal state recovered, no duplicates (T1b/c).
2. **The 002 ECS-only-field gap closes for rewind scenarios**: snapshots capture full
   entity records, so UI-only fields (`hovered`, `dragCount`) come back with the
   restore (T1d). The gap remains only for SSE remove/re-add flicker, where no snapshot
   boundary is involved.
3. Restore marks every entity dirty (T1e) so downstream consumers — 006 delta contexts,
   the buffered React Flow patch loop — observe the rewind instead of silently holding
   stale state. Without this, the next LLM delta would omit the rewind entirely.
4. Replay from an empty world + 5 semantic events reproduced the live state exactly
   (T2). Determinism holds *because* the mediation layer is the single write path —
   replay re-runs `propose→approve`, and a replay divergence throws instead of
   silently corrupting.
5. Undo/redo: snapshot marks pair with event-log offsets; undo-2 landed precisely
   between operations A and B, redo via log replay returned byte-identical head state
   (T3). No inverse-operation machinery needed.
6. Memory: 4.2 KB/snapshot at 26 entities, 78.4 KB at 400. A 20-deep ring costs 85 KB /
   1.5 MB respectively — negligible for a browser page.

## Results

**Verdict: ✓ VALIDATED** — 9/9 checks.

- Snapshot ring + event log is a complete history mechanism at ~80 LOC, with no
  library support required beyond 005b's canonical serializer.
- Event-sourced redo (replay from mark) beats storing inverse ops: it reuses the
  mediation layer verbatim and inherits its validation.
- Constraint: replaying `sync` events requires logging full snapshot payloads (memory
  grows with session length) — the real build should checkpoint (drop log prefix at
  each ring snapshot) exactly as the ring/marks pairing here demonstrates.
- Constraint: `restoreSnapshot` must run inside the same discipline as the sync writer
  (it is a third writer in the 007 sense); it clears and re-marks dirty state itself.
