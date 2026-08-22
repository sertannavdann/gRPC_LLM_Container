---
spike: 006
name: delta-context-streaming
type: standard
validates: "Given an SSE-churning world and iterative LLM invocations, when invocation n receives only entities changed since n−1, then deltas apply correctly (mirror reconstruction) and cut token cost vs full snapshots — and bitECS's native delta machinery either serves this or doesn't"
verdict: VALIDATED
related: [005a-world-snapshot-bitecs, 005b-world-snapshot-miniplex, 002-ecs-xstate-coexistence]
tags: [ecs, deltas, context-engineering, tokens, bitecs, miniplex]
---

# Spike 006: Delta-Context Streaming

## What This Validates

The taxonomy's Iterative pattern (AutoDroid-style: re-invoke the LLM with updated
environment state) combined with the survey's context-compression principle: invocation
*n* receives a **delta** — changed/added entities + removed ids since invocation *n−1* —
instead of a full world snapshot. Correctness is proven by reconstructing an "LLM mental
model" mirror from deltas alone and comparing it to the true world at every invocation.

Also answers bitECS's last open card from 005: is `ObserverSerializer` + SoA `diff` mode
usable for *context* deltas?

## How to Run

```bash
npm install
node run.mjs               # main rig: 40-tick churn session, delta vs full accounting
node sensitivity.mjs       # savings as a function of world size, fixed churn rate
node probe-bitecs-delta.mjs # bitECS observer/diff machinery + set()/onSet choke point
```

## Investigation Trail

1. Main rig (miniplex world, per 005 verdict): 40 SSE-like ticks (seeded LCG churn:
   metric jitter, status flips, occasional module remove/re-add), LLM invocation every
   5 ticks. Dirty tracking = a `Set` of logical ids populated by `add/remove/mutate`
   choke-point helpers — **the whole tracker is 32 lines** and is the same discipline the
   002 sync-contract already imposes.
2. Delta format: compact-dsl lines for changed entities + a `removed:` line + a header
   declaring "unchanged entities omitted". Mirror reconstruction from deltas matched the
   true world at **all 8 invocations**.
3. Token accounting at 26 entities under heavy churn (≈half the world changes between
   invocations): **45.3% saved** vs full snapshots.
4. Sensitivity at fixed absolute churn (the realistic regime — SSE ticks touch a handful
   of entities regardless of world size): 49.2% saved at N=26, **82.5% at N=100, 95.2%
   at N=400**. Delta cost is O(churn), full-snapshot cost is O(world). The strategy's
   value grows directly with canvas scale.
5. bitECS probe Q1: serializers return opaque `ArrayBuffer`s; **no API exposes which
   entities changed**, so text deltas cannot be derived from the native machinery — it
   exists to feed the paired binary deserializer (network sync), a role NEXUS's SSE
   stream already fills.
6. bitECS probe Q2: wire sync works and is impressively compact (13 B for one f32
   change) — but diff mode never transmits values equal to the shadow's initial zero,
   leaving `undefined` holes in the mirror's arrays ("unchanged from 0" is
   indistinguishable from "never sent"). A subtle correctness tax on the wire path.
7. bitECS probe Q3: `set()` + `observe(onSet)` does work as a native dirty-set choke
   point — but direct array writes silently bypass it, so it is convention-enforced
   exactly like miniplex's `mutate()` helper, at more ceremony.

## Results

**Verdict: ✓ VALIDATED** — for the delta-context *strategy*, on miniplex, with the
hand-rolled dirty set.

- Delta streaming is correct (mirror-proven) and the token win is decisive, scaling
  from ~50% to ~95% as the world grows. This directly implements the survey's
  compression/assembly guidance for `c_state`.
- The tracker is trivial (32 lines) *because* the 002 ownership contract already forces
  all mutations through choke points. Architecture compounds: the discipline bought for
  correctness in 002 buys delta streaming almost for free.
- **bitECS's native delta machinery is confirmed irrelevant to the context role** —
  opaque packets, no change-set accessor, zero-skip gotcha. Combined with 005, both
  halves of the "bitECS presumptive winner" hypothesis are now empirically closed:
  **miniplex remains the library for the tri-consumer substrate.**
- Delta framing note: the header must explicitly say unchanged entities are omitted, or
  the model may treat the delta as the full world. (Prompt-level, verified by
  construction here; behavioral testing with a live model is out of spike scope.)
