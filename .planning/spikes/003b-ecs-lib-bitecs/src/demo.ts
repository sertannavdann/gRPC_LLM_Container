// Same scenario as 003a-ecs-lib-miniplex/src/demo.ts: module blueprint
// entities for the pipeline canvas (id, label, status, position,
// credentialsRequired). API confirmed against node_modules/bitecs/docs/API.md
// and node_modules/bitecs/test/core/*.test.ts (0.4.0 — defineComponent/
// defineQuery were removed in this version; components are plain objects,
// query() is called directly).
import { createWorld, addEntity, removeEntity, addComponent, query } from "bitecs";
// NOTE: `set()` is deliberately NOT used here. See debug-query.ts and the
// README's Investigation Trail — set()/addComponent(world, eid, set(C, data))
// silently does nothing to a component's storage unless you've separately
// registered an onSet observer via observe(world, onSet(C), writerFn). That
// mechanism exists for inheritance/prefab scenarios; for plain writes the
// working, idiomatic pattern is addComponent() to register presence, then
// direct array assignment.

const STATUS_NAMES = ["idle", "building", "validating", "validated", "error"] as const;
type StatusName = (typeof STATUS_NAMES)[number];
const STATUS_CODE: Record<StatusName, number> = Object.fromEntries(
  STATUS_NAMES.map((s, i) => [s, i])
) as Record<StatusName, number>;

// --- Numeric components: bitECS's actual strong case (typed-array-shaped SoA). ---
const Position: { x: number[]; y: number[] } = { x: [], y: [] };
const Status: { value: number[] } = { value: [] };

// --- Non-numeric data has no natural typed-array representation, so it falls
// back to plain JS arrays WE manage ourselves, indexed by eid. This is the
// same mechanical shape as the "real" components above, but none of the
// perf benefit, and — critically — bitECS does NOT know these arrays exist,
// so it does nothing to clean them up when an entity is removed. ---
const IdString: string[] = [];
const Label: string[] = [];
const CredentialsRequired: string[][] = [];

const world = createWorld();

function addModule(idStr: string, label: string, status: StatusName, x: number, y: number, creds: string[]) {
  const eid = addEntity(world);
  addComponent(world, eid, Position);
  addComponent(world, eid, Status);
  Position.x[eid] = x;
  Position.y[eid] = y;
  Status.value[eid] = STATUS_CODE[status];
  IdString[eid] = idStr;
  Label[eid] = label;
  CredentialsRequired[eid] = creds;
  return eid;
}

const seed: Array<[string, string, StatusName, string[]]> = [
  ["weather", "Weather Adapter", "validating", ["OPENWEATHER_API_KEY"]],
  ["calendar", "Google Calendar", "validated", ["GOOGLE_OAUTH_TOKEN"]],
  ["gaming", "Clash Royale", "idle", ["CR_API_TOKEN"]],
  ["finance", "CIBC CSV", "building", []],
  ["showroom", "Showroom Demo", "validating", []],
];

const eidByDomainId: Record<string, number> = {};
seed.forEach(([id, label, status, creds], i) => {
  eidByDomainId[id] = addModule(id, label, status, i * 120, 0, creds);
});

console.log("--- bitecs demo ---");
const all = query(world, [Status]);
console.log(`total entities: ${all.length}`);

// Query: entity IDs matching a component set, then manual value filtering
// (bitECS queries are presence-based over component arrays, same limitation
// as miniplex — value filtering is always a manual .filter() afterward in
// both libraries for this kind of domain).
const validating = all.filter((eid) => Status.value[eid] === STATUS_CODE.validating);
console.log(
  `validating (${validating.length}):`,
  validating.map((eid) => Label[eid])
);

// Mutate a component value — direct SoA array write, not entity.field.
const weatherEid = eidByDomainId["weather"];
Status.value[weatherEid] = STATUS_CODE.validated;
console.log(`after mutation, weather status = ${STATUS_NAMES[Status.value[weatherEid]]}`);

// Remove an entity.
const financeEid = eidByDomainId["finance"];
removeEntity(world, financeEid);
console.log(`after removal: ${query(world, [Status]).length} entities remain`);

// GOTCHA: removeEntity() only cleared bitECS's own registered stores
// (Position, Status via addComponent). It has no idea IdString/Label/
// CredentialsRequired exist, because we built those ourselves outside its
// component system. They still hold stale data:
console.log(`stale Label[financeEid] after removal (bitECS didn't clear it): "${Label[financeEid]}"`);

// Re-add — bitECS recycles eids. If the new "finance" entity happens to get
// the SAME eid back, our manual arrays already have (correct, coincidentally
// matching) old data at that slot — but that's luck, not correctness. Prove
// it by adding a DIFFERENT module first (to *not* immediately recycle the
// same slot) then removing the label manually to show it's OUR job:
delete (Label as unknown as Record<number, string>)[financeEid];
const newFinanceEid = addModule("finance", "CIBC CSV v2", "idle", 3 * 120, 0, []);
console.log(`re-added finance as eid=${newFinanceEid} (was eid=${financeEid}); recycled: ${newFinanceEid === financeEid}`);
console.log(`Label at new eid: "${Label[newFinanceEid]}"`);

console.log(
  "all entities:",
  query(world, [Status]).map((eid) => `${IdString[eid]}:${STATUS_NAMES[Status.value[eid]]}`)
);
