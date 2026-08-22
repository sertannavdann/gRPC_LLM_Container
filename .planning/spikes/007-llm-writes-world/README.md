---
spike: 007
name: llm-writes-world
type: standard
validates: "Given schema-validated mutation ops from an LLM component, when applied through a single mediation function alongside SSE sync, then staged/live state coexist and the 002 ownership contract survives two writers"
verdict: VALIDATED
related: [002-ecs-xstate-coexistence, 006-delta-context-streaming, 008-snapshot-replay-and-rewind]
tags: [ecs, llm-output, approval-gates, mediation, ownership]
---

# Spike 007: LLM Writes World

## What This Validates

The return path of the tri-consumer substrate: an LLM component (taxonomy: Output
Consumer = Program, Output Format = Structure) emits mutation ops as structured JSON;
a single mediation layer validates them (schema + referential + ownership policy),
stages them as proposals (Phase 8 approval gates = the taxonomy's Revision dimension),
and applies approved ops through the same primitives the SSE sync writer uses.

## How to Run

```bash
npm install && node run.mjs   # 17-check rig, exits non-zero on failure
```

## Investigation Trail

1. Op vocabulary: `set_status`, `set_credentials`, `move`, `add_module`,
   `remove_module` — each with schema fields AND a `kinds` allow-list encoding the
   ownership policy (LLM may add/remove *modules* only; services/stages are read-only
   to it; existence stays XState/SSE-owned).
2. Proposals are staged: `propose()` validates immediately (fast feedback to the LLM),
   but nothing touches the live world. `previewViews()` overlays staged ops for the UI
   panel without mutation (T1d proved).
3. Re-validation happens at **three** points: proposal time, every SSE snapshot sync
   (the 002 `clearSelectionIfMissing` pattern generalized — a snapshot that removes a
   proposal's target invalidates the proposal *in the same transition*, T4b), and
   approval time (catches non-sync races, T5).
4. Approved ops flow through the same add/remove/mutate primitives as SSE sync — so
   they feed the 006 dirty set for free (T1f): approved changes appear in the next
   delta context without extra wiring.
5. T6 probed the optimistic-update lifecycle: approved `add_module` creates the entity
   locally; a confirming SSE snapshot converges without duplicates; but a snapshot
   **without** the module removes it (T6c) — correct per the existence-authority
   contract, but it means a real backend round-trip slower than one SSE tick will
   flicker the new module out and back. Needs a pending-confirmation grace period in
   the real build (same class as the known 002 transient-absence gap).

## Results

**Verdict: ✓ VALIDATED** — 17/17 checks.

- Staged-vs-live coexistence works cleanly in one world + a proposals map; no second
  world or store needed. Preview is a pure overlay.
- The two-writer problem dissolves when both writers share one mediation path and
  proposals are re-validated on every snapshot; no conflict case survived to corrupt
  state in any test.
- Structured, actionable error strings (`entity "mod-ghost" does not exist (stale
  proposal?)`) are exactly what the taxonomy's Program-consumer pattern wants to feed
  back into the next LLM invocation.
- **Constraint for the real build:** optimistic `add_module` needs pending-confirmation
  handling (grace period or `pendingSince` timestamp honored by the sync writer) or
  approved additions will flicker until the backend's next snapshot includes them.
- Hand-rolled validator is spike-grade; use zod in `ui_service` (matches existing
  TypeScript stack) with the same three re-validation points.
