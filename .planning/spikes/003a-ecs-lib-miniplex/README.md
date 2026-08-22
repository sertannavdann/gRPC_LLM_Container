---
spike: 003a
name: ecs-lib-miniplex
type: comparison
validates: "Given the same entity/component set (module blueprint, position, status, credentials), when implemented in miniplex vs bitECS, then which offers better TypeScript ergonomics + React hook integration for this HMI use case"
verdict: WINNER
related: [003b-ecs-lib-bitecs]
tags: [ecs, miniplex, comparison]
---

# Spike 003a: ecs-lib-miniplex (comparison winner)

Comparison spike, built back-to-back with
[003b-ecs-lib-bitecs](../003b-ecs-lib-bitecs/README.md) against the identical scenario: module
blueprint entities (id, label, status, position, credentialsRequired) for the pipeline canvas.

## What This Validates

Same scenario in both libraries — which gives better TypeScript ergonomics and is a better fit
for React integration, for NEXUS's specific domain (dozens of entities, string-heavy data, no
hot per-frame simulation loop)?

## Research

See `003b-ecs-lib-bitecs/README.md` for bitECS's research trail. For miniplex: confirmed from
`node_modules/miniplex-react/README.md` (already read in spike 001) that entities are plain JS
objects and components are just properties — no separate storage model to learn.

## How to Run

```bash
cd .planning/spikes/003a-ecs-lib-miniplex
npm install
npm run demo                # src/demo.ts
npx tsc --noEmit --strict --target es2020 --lib es2020 --moduleResolution bundler --module esnext src/type-error-check.ts
```

Then compare against `../003b-ecs-lib-bitecs` (`npm install && npm run demo` there too).

## What to Expect

Both demos perform the identical sequence: seed 5 modules, query by status="validating", mutate
one, remove one, re-add one, print final state.

## Investigation Trail

1. Built the miniplex demo first (`demo.ts`) — worked correctly on the first run, no surprises:
   ```
   validating (2): [ 'Weather Adapter', 'Showroom Demo' ]
   after mutation, weather.status = validated
   after removal: 4 entities remain
   after re-add: 5 entities
   all entities: [ 'weather:validated', 'calendar:validated', 'gaming:idle', 'showroom:validating', 'finance:idle' ]
   ```
2. Built the bitECS demo to the same spec. **First attempt silently produced wrong data**
   (`validating (0): []`, all statuses `undefined` after remove/re-add) because of the
   `set()`/`onSet` observer requirement documented in 003b's Investigation Trail — this alone is
   a significant ergonomics data point: the miniplex version needed zero debugging, the bitECS
   version needed a dedicated follow-up investigation (`debug-query.ts`) to even get correct
   results.
3. Ran the type-error checks side by side (both via `tsc --noEmit --strict`):

   | Case | miniplex | bitECS |
   |---|---|---|
   | Typo'd field name | ✅ caught (`TS2551`) | ✅ caught (`TS2551`, same mechanism — plain object) |
   | Invalid value not in union/wrong type | ✅ caught (`TS2322`) | ✅ caught (`TS2322`) |
   | Missing required field on creation | ✅ caught (`TS2345`, structural completeness) | N/A — no equivalent single "create" call; component presence is per-`addComponent` call, un-typed at the entity level |
   | Reading a field the entity never had | ✅ caught — the field doesn't exist on the type unless it was added to the entity's declared shape | ❌ **not caught** — `Status.value[neverAddedEid]` compiles and silently returns `undefined` |

4. Compared code shape for the domain's non-numeric fields (`label: string`,
   `credentialsRequired: string[]`):
   - **miniplex:** identical treatment to numeric fields — just object properties.
   - **bitECS:** falls outside the SoA typed-array model entirely; requires hand-rolled parallel
     arrays (`Label: string[]`, `CredentialsRequired: string[][]`) that bitECS's own
     `removeEntity`/id-recycling machinery knows nothing about, so cleanup on removal is the
     caller's responsibility (demonstrated concretely in 003b: a stale label survived entity
     removal and would have leaked into a recycled eid slot).
5. **Performance was not empirically benchmarked** — at NEXUS's actual scale (dozens of pipeline
   nodes, not thousands), bitECS's documented SoA/cache-locality advantage has no realistic
   opportunity to matter, so a micro-benchmark wasn't worth the time for this comparison. This is
   a scale judgment, not a measured one — worth revisiting only if the pipeline canvas were ever
   expected to hold thousands of live entities, which nothing in the current NEXUS architecture
   suggests.

## Results

**Verdict: miniplex WINS for this use case.**

| Dimension | miniplex | bitECS | Winner |
|---|---|---|---|
| TypeScript ergonomics | Full structural typing, entity-level field safety | Value/field typos caught; **entity-level component presence not typed** | miniplex |
| Time-to-correct | Correct on first run | Required debugging a silent no-op (`set()` without `onSet`) | miniplex |
| Non-numeric data (labels, credential lists) | Native — just object fields | Requires hand-rolled, unmanaged parallel arrays | miniplex |
| Entity add/remove/re-add hygiene | Automatic — new plain object each time, no stale state possible | Manual — caller must clean up any side-arrays on removal to avoid stale-data-on-recycle | miniplex |
| React integration (spikes 001/002's buffered pattern) | Plain objects map directly into React state/props | Same is possible, but requires "eid → props" translation through separate array lookups per field | miniplex |
| Raw throughput at scale (thousands of entities, per-frame loops) | Not miniplex's strength | bitECS's actual strength | bitECS (irrelevant at NEXUS's scale) |

**Impact on remaining spikes:** Spike 004 (systems as canvas behaviors) will use miniplex, per
this result — matching the library already used in spikes 001 and 002.

**Requirement added to MANIFEST.md:** use miniplex (not bitECS) if/when this idea moves past
spiking — bitECS's cost profile doesn't fit NEXUS's pipeline-canvas domain (dozens of
string-labeled entities, no hot simulation loop).
