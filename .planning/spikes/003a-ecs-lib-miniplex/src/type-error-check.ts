// Deliberately-wrong code, to check what TypeScript catches. Run via:
//   npx tsc --noEmit src/type-error-check.ts
// (expected to FAIL to compile — that's the point)
import { World } from "miniplex";

type Status = "idle" | "building" | "validating" | "validated" | "error";
type ModuleEntity = {
  id: string;
  label: string;
  status: Status;
  position: { x: number; y: number };
  credentialsRequired: string[];
};

const world = new World<ModuleEntity>();
const e = world.add({
  id: "x",
  label: "X",
  status: "idle",
  position: { x: 0, y: 0 },
  credentialsRequired: [],
});

// (1) typo'd field name — should be a compile error (plain object, full
// structural typing).
console.log(e.statuss);

// (2) invalid status value not in the union — should be a compile error.
e.status = "not-a-real-status";

// (3) missing required field on add() — should be a compile error.
world.add({ id: "y", label: "Y", status: "idle" });
