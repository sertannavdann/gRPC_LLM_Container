// What TypeScript catches vs. doesn't for bitECS's SoA shape. Run via:
//   npx tsc --noEmit --strict --target es2020 --lib es2020 src/type-error-check.ts
import { createWorld, addEntity } from "bitecs";

const Status: { value: number[] } = { value: [] };
const world = createWorld();
const eid = addEntity(world);

// (1) wrong VALUE type — DOES get caught, because we explicitly annotated
// `Status: { value: number[] }`. If we'd let TS infer the type from `{ value: [] }`
// alone, it would infer `never[]`, which also happens to catch this — but for a
// different, less useful reason (nothing is assignable to never[]).
Status.value[eid] = "not-a-number";

// (2) wrong FIELD name on the component object — DOES get caught, same as
// any plain object typo (Status is a plain, explicitly-typed object).
console.log(Status.values);

// (3) THE GAP: reading a component array at an eid that was NEVER given
// this component (no addComponent(world, eid2, Status) call) — does NOT get
// caught. There is no per-entity type that says "this eid has Status."
// TypeScript sees `number[]`, indexing it with any `number` type-checks
// fine, and returns `undefined` at runtime — a silent bug, not a compile
// error. This is the direct cost of SoA: components are arrays indexed by a
// bare `number`, not properties on a typed entity object.
const neverAddedEid = 9999;
const bogus: number = Status.value[neverAddedEid]; // compiles; is `undefined` at runtime
console.log("bogus read compiles fine, runtime value:", bogus);
