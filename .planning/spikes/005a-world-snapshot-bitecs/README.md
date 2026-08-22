---
spike: 005a
name: world-snapshot-bitecs
type: comparison
validates: "Given the pipeline world in bitECS (str()-branded strings, no interning), when serialized to a canonical structured c_state and a binary snapshot, then it is deterministic, round-trip faithful, and cheaper than miniplex on the same criteria"
verdict: INVALIDATED
related: [005b-world-snapshot-miniplex, 003b-ecs-lib-bitecs, 006-delta-context-streaming]
tags: [ecs, bitecs, serialization, context-engineering, snapshots]
---

# Spike 005a: World Snapshot as Context — bitECS

## What This Validates

Given the pipeline world (26 string-heavy entities: services/modules/stages, modeled on
the real SSE pipeline-state shape) stored in bitECS 0.4.0, when serialized into (a) an
LLM-legible structured `c_state` text and (b) a binary snapshot for rewind/replay, then
serialization is deterministic under churn, round-trip faithful, token-efficient, and
cheaper than the miniplex equivalent (005b) — the criteria that would justify reversing
the 003a/b verdict for the context-substrate role.

Motivated by *A Survey of Context Engineering for LLMs* (context as `C = A(c1..cn)`;
`c_state` from world state; structured-beats-prose; snapshot/restore as a core context
manager capability) and *LLMs as Software Components* (Prompt State = Program).

## Research

Verified against installed `bitecs@0.4.0` source (`dist/serialization/index.d.ts`,
`docs/Serialization.md`) — the 003b convention, since docs alone misled us before:

- `bitecs/serialization` exports `createSnapshotSerializer/Deserializer`,
  `createSoASerializer/Deserializer` (with **`diff: true` mode**, epsilon-compared),
  `createAoSSerializer`, `createObserverSerializer/Deserializer`.
- **Surprise: native string support.** `str([])`-branded arrays and `array(str)` string
  lists serialize via TextEncoder — the hand-rolled string-interning layer this spike
  planned for is unnecessary. (003b's assumption was wrong in bitECS's favor.)
- Snapshot serializer takes `(world, components, buffer?)`; default backing buffer is
  100MB — pass a small `ArrayBuffer` explicitly.
- The 003b `set()`/`onSet` footgun avoided throughout: `addComponent` + direct array
  writes only.

## How to Run

```bash
npm install
node run.mjs            # main rig: round-trip, determinism, cost, tokens, LOC
node probe-fairness.mjs # numeric-only large-N probe + rewind-into-drifted-world probe
```

## What to Expect

`run.mjs` prints round-trip OK, text-determinism OK, binary-determinism UNSTABLE,
benchmark numbers, and token counts per format. `probe-fairness.mjs` prints the
numeric-only head-to-head and the rewind gotcha.

## Investigation Trail

1. Built world with `str()`/`array(str)` components directly — no interning layer.
   Round-trip through `SnapshotSerializer` into a **fresh world** worked first try,
   including UTF-8 labels and string-array credentials. 2,855 bytes for 26 entities.
2. f32 precision bit immediately: `12.4` stored as `12.399999618530273`. The view layer
   needs 1dp rounding (or `f64` components) to recover fixture values. Wrapper tax.
3. Churn test (remove 3, re-add in different order, revert a mutation): the canonical
   `c_state` text is stable (the verbalizer's sort-by-logical-id does the work), but the
   **binary snapshot is not byte-stable** — eid recycling reorders the packet. Binary
   snapshots can't be hashed/compared for "did anything change" or prompt-cache reuse.
4. Benchmarks, 26 entities: binary snapshot **0.200 ms/op** vs text-c_state 0.008 ms/op.
   At 5,000 entities: 4.11 ms vs 1.37 ms. The binary path is the *slow* path.
5. Fairness probe A — numeric-only components (bitECS's home grain), SoA serializer,
   N=5,000 and N=50,000: **0.25 vs 0.23 ms** and **2.69 vs 2.36 ms** against plain
   `JSON.stringify` objects. No crossover in bitECS's favor even at 50k numeric entities.
6. Fairness probe B — restore old snapshot into the **same drifted world**: the
   deserializer **duplicated** the packet entity instead of matching the live one
   (3 entities after restore), did not rewind the mutated value, and kept the
   post-snapshot entity. Same-world rewind requires clear-first or explicit idMap
   bookkeeping. (Direct input to spike 008.)

## Results

**Verdict: ✗ INVALIDATED** (as the presumptive winner for the snapshot half of the
context-substrate role — see 005b for the head-to-head table).

- Everything *works*: strings, string arrays, fresh-world round-trip, deterministic
  c_state text. bitECS *can* do this job.
- But every criterion that was supposed to be decisive for bitECS measured **against**
  it on this workload: binary snapshot 40× slower than miniplex's canonical JSON at
  realistic scale, non-canonical bytes under churn, more glue (66 vs 39 LOC), f32
  precision tax, and a duplicate-on-restore rewind gotcha.
- Token cost of `c_state` is **library-independent** — identical by construction, since
  the verbalizer reads canonical views. Format choice dominates: compact-dsl 752 tokens
  vs pretty-JSON 2,175 (2.9×) for the same 26 entities.
- bitECS's remaining card is delta streams (`ObserverSerializer` + SoA `diff` mode) —
  spike 006's question, not prejudged here.
