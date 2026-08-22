// Same scenario as 003b-ecs-lib-bitecs/src/demo.ts: module blueprint entities
// for the pipeline canvas (id, label, status, position, credentialsRequired).
// Domain note: NEXUS pipeline entities are string-labeled, have a
// string[] of required credentials, and number in the dozens — not the
// thousands-of-numeric-entities case ECS libraries are usually built for.
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

const seed: Omit<ModuleEntity, "position">[] = [
  { id: "weather", label: "Weather Adapter", status: "validating", credentialsRequired: ["OPENWEATHER_API_KEY"] },
  { id: "calendar", label: "Google Calendar", status: "validated", credentialsRequired: ["GOOGLE_OAUTH_TOKEN"] },
  { id: "gaming", label: "Clash Royale", status: "idle", credentialsRequired: ["CR_API_TOKEN"] },
  { id: "finance", label: "CIBC CSV", status: "building", credentialsRequired: [] },
  { id: "showroom", label: "Showroom Demo", status: "validating", credentialsRequired: [] },
];

for (const [i, s] of seed.entries()) {
  world.add({ ...s, position: { x: i * 120, y: 0 } });
}

console.log("--- miniplex demo ---");
console.log(`total entities: ${world.entities.length}`);

// Query: plain object entities, `.with()` filters by presence of a
// component key — here every entity has every key, so this is more useful
// as a value-filtered query via .filter() / manual iteration, since
// miniplex's built-in query is presence-based, not value-based.
const validating = world.entities.filter((e) => e.status === "validating");
console.log(
  `validating (${validating.length}):`,
  validating.map((e) => e.label)
);

// Mutate a component value directly — plain property assignment.
const weather = world.entities.find((e) => e.id === "weather")!;
weather.status = "validated";
console.log(`after mutation, weather.status = ${weather.status}`);

// Remove an entity.
const finance = world.entities.find((e) => e.id === "finance")!;
world.remove(finance);
console.log(`after removal: ${world.entities.length} entities remain`);

// Re-add — a brand new plain object, no special API needed.
world.add({ id: "finance", label: "CIBC CSV", status: "idle", position: { x: 3 * 120, y: 0 }, credentialsRequired: [] });
console.log(`after re-add: ${world.entities.length} entities`);

console.log("all entities:", world.entities.map((e) => `${e.id}:${e.status}`));
