---
spike: 005b
name: world-snapshot-miniplex
type: comparison
validates: "Given the same pipeline world in miniplex with a hand-rolled canonical-JSON snapshot, when measured on the same context-substrate criteria as 005a, then compare head-to-head"
verdict: WINNER
related: [005a-world-snapshot-bitecs, 003a-ecs-lib-miniplex]
tags: [ecs, miniplex, serialization, context-engineering, snapshots]
---

# Spike 005b: World Snapshot as Context — miniplex

## What This Validates

Same fixture, same verbalizer, same measurements as 005a, with miniplex 2.0 plain-object
entities and a hand-rolled snapshot layer (canonical sorted JSON + a structuredClone
variant), since miniplex ships no serialization.

## How to Run

```bash
npm install
node run.mjs
```

## Investigation Trail

1. World adapter is 39 non-comment lines total — `views()` is nearly the identity
   function because entities already *are* plain records.
2. Round-trip: exact (string-keyed JSON; no float precision loss, no enum tables).
3. Churn test: canonical JSON snapshot is **byte-stable** (sort-by-id happens inside
   `serialize()`), c_state text stable, restore-then-verbalize stable.
4. Benchmarks, 26 entities: JSON snapshot **0.005 ms/op**, structuredClone 0.021 ms/op,
   text-c_state 0.006 ms/op. At 5,000 entities: 1.05 / 3.54 / 1.29 ms.
5. Token counts identical to 005a by construction (shared verbalizer) — confirming the
   token-efficiency criterion does not discriminate libraries.

## Results — Head-to-Head Verdict (005a vs 005b)

**Verdict: ✓ WINNER.** miniplex + ~40 lines of hand-rolled canonical JSON beats bitECS's
built-in serialization module on every measured context-substrate snapshot criterion:

| Criterion (26-entity realistic scale) | bitECS 005a | miniplex 005b |
|---|---|---|
| Snapshot round-trip fidelity | OK, needs f32 1dp rounding | OK, exact |
| c_state text deterministic after churn | OK | OK |
| Snapshot bytes canonical after churn | ✗ (eid recycling) | ✓ (sorted JSON) |
| Snapshot cost | 0.200 ms | **0.005 ms** |
| Snapshot cost @5,000 entities | 4.11 ms | **1.05 ms** |
| Same-world rewind | duplicates entities (gotcha) | clear-first built into adapter |
| c_state tokens (compact-dsl) | 752 | 752 (identical) |
| Adapter glue | 66 LOC | **39 LOC** |
| Numeric-only 50k-entity fairness probe | 2.69 ms | 2.36 ms (plain JSON) |

The "bitECS presumptive winner" hypothesis from the context-engineering reframing is
**invalidated for snapshots**: its serialization module solves wire-transfer problems
(binary compactness, id remapping across worlds), not context-substrate problems
(canonical text, cheap deterministic capture, LLM legibility). The papers' criteria are
real — but they're satisfied by a verbalization layer + canonical ordering, which are
library-independent, and miniplex produces the canonical views with less code and less
ceremony. bitECS's last distinct advantage (observer/diff delta streams) is spike 006.

## Key transferable findings (either library)

- **Canonical ordering is the verbalizer's job.** Entity iteration order is unstable
  under churn in both libraries; sort by logical string id before serializing anything.
- **Format dominates token cost**: compact-dsl 752 / table 853 / compact-JSON 1,288 /
  pretty-JSON 2,175 tokens for the same 26 entities. Never dump raw JSON into context.
- **Rewind = clear-then-restore into a fresh/cleared world.** In-place restore over a
  drifted world is unsafe in bitECS (duplicates) and only safe in the miniplex adapter
  because it clears first.
