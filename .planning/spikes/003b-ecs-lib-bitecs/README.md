---
spike: 003b
name: ecs-lib-bitecs
type: comparison
validates: "Given the same entity/component set (module blueprint, position, status, credentials), when implemented in bitECS, then does it offer good TypeScript ergonomics/React integration for this HMI use case"
verdict: INVALIDATED (loses to miniplex for this use case)
related: [003a-ecs-lib-miniplex]
tags: [ecs, bitecs, comparison]
---

# Spike 003b: ecs-lib-bitecs

Comparison spike — see [003a-ecs-lib-miniplex/README.md](../003a-ecs-lib-miniplex/README.md) for
the head-to-head verdict. This file documents bitECS's side of the comparison and the
investigation trail specific to it.

## What This Validates

Same scenario as 003a: module blueprint entities (id, label, status, position,
credentialsRequired) for the pipeline canvas — implemented in bitECS 0.4.0 instead of miniplex.

## Research

Confirmed the real 0.4.0 API from source, not memory (0.3→0.4 removed `defineComponent`/
`defineQuery` — a version mismatch would have produced misleading results):
- `node_modules/bitecs/docs/API.md`
- `node_modules/bitecs/test/core/Component.test.ts`, `Query.test.ts`, `Observer.test.ts`

Components are plain objects with array fields (SoA): `{ x: number[], y: number[] }`. Entities
are bare numeric ids. `addComponent(world, eid, Component)` registers presence; `query(world,
[Component, ...])` returns matching eids.

## How to Run

```bash
cd .planning/spikes/003b-ecs-lib-bitecs
npm install
npm run demo                      # node scripts/demo.ts output, see below
npx tsx src/debug-query.ts        # isolates the set()/onSet finding
npx tsc --noEmit --strict --target es2020 --lib es2020,dom --moduleResolution bundler --module esnext src/type-error-check.ts
```

## What to Expect

`demo.ts` seeds 5 module entities, queries by status, mutates one, removes one, and re-adds one —
same operations as 003a's demo, for direct comparison.

## Investigation Trail

1. **First attempt used the documented `set()` helper** (per `docs/API.md`: "Sets component data
   on an entity" and the pattern visible in `Component.test.ts`:
   `addComponent(world, eid, set(Position, { x: 1, y: 1 }))`). Ran the demo — no compile error, no
   runtime error, but **`validating (0): []`** when 2 entities should have matched, and every
   entity's status printed `undefined` after a remove/re-add cycle.
2. **Follow-up (`debug-query.ts`)**, isolating just `addEntity` + `addComponent(world, eid,
   set(Status, {value: 2}))`: `hasComponent` returns `true`, `query()` finds the entity
   correctly, but **`Status.value` stays `[]`** — the value was never actually written anywhere.
3. **Root cause, found by reading `Observer.test.ts`:** `set()` only *tags* data as
   `{component, data}`. Whether that data is ever written into a component's storage depends
   entirely on whether an `onSet` **observer** has been separately registered:
   `observe(world, onSet(Position), (eid, params) => { Position.x[eid] = params.x; ... })`. This
   mechanism exists to support entity inheritance/prefab copying (confirmed by
   `Observer.test.ts`'s "should properly inherit component values with onSet and onGet
   observers" test) — it is not, despite how the docs and the common test-file pattern read, a
   general "just write the values" API. **Without registering an observer per component, `set()`
   is a silent no-op:** no type error, no runtime error, no warning — just empty arrays and
   `undefined` reads downstream. This is a real landmine for anyone learning bitECS from its own
   docs/tests without realizing the observer step is required.
4. **Fixed by switching to the actually-idiomatic simple pattern:** `addComponent(world, eid,
   Component)` to register presence, then direct array writes
   (`Position.x[eid] = x`). Re-ran — correct results across the board (see `demo.ts` output in
   the sibling README's comparison table).
5. **Non-numeric data gotcha:** `id`/`label`/`credentialsRequired` are strings/string-arrays —
   bitECS's SoA arrays are only really suited to numeric/typed-array data. These fields have to
   be hand-rolled as plain parallel arrays (`Label: string[] = []`) that bitECS knows nothing
   about. Demonstrated concretely: after `removeEntity(world, financeEid)`, `Label[financeEid]`
   still held the stale `"CIBC CSV"` string — bitECS only clears the stores it manages
   (`Position`, `Status` via `addComponent`), not arrays the caller manages independently. A
   subsequent `addEntity()` recycled the exact same `eid`, so the stale label would have silently
   resurfaced had the demo not explicitly cleared it first.
6. **Type-safety check (`type-error-check.ts`, `tsc --noEmit --strict`):**
   - Wrong value type (`Status.value[eid] = "not-a-number"`) → **caught** (`TS2322`).
   - Typo'd field name (`Status.values`) → **caught** (`TS2551`, same as any plain object).
   - Reading a component array **at an eid that never had the component added**
     (`Status.value[9999]`) → **not caught**. Compiles cleanly; returns `undefined` at runtime.
     There is no per-entity type tracking "which components does this eid actually have" — that
     information only exists at runtime, via `hasComponent()`. This is the direct structural cost
     of SoA: components are arrays indexed by a bare `number`, not properties on a typed entity
     object, so there's nothing for TypeScript to narrow against.

## Results

**Verdict: INVALIDATED for this use case** (bitECS itself works — it's a solid library — but it's
the wrong tool for NEXUS's pipeline-canvas domain specifically). See 003a's README for the full
head-to-head table and reasoning. Summary: bitECS's SoA design pays off at thousands-of-entities,
tight-loop, numeric-heavy scale (its intended domain — physics, particle systems). NEXUS's
pipeline canvas has dozens of entities with string-heavy data (labels, credential lists) and no
hot per-frame simulation loop — none of bitECS's actual strengths apply, while its costs
(hand-rolled non-numeric storage, manual id-recycling cleanup, weaker per-entity type safety, and
an easy-to-hit `set()`/`onSet` footgun) all do.
