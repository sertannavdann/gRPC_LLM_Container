// Follow-up: demo.ts showed "validating (0): []" when 2 entities should
// match, and after remove+re-add ALL entities except one showed status
// "undefined". Debug from scratch, printing raw arrays at each step.
import { createWorld, addEntity, removeEntity, addComponent, query, set, hasComponent } from "bitecs";

const Status: { value: number[] } = { value: [] };
const world = createWorld();

const e0 = addEntity(world);
addComponent(world, e0, set(Status, { value: 2 }));
console.log("e0 =", e0, "hasComponent:", hasComponent(world, e0, Status), "Status.value =", Status.value);

const e1 = addEntity(world);
addComponent(world, e1, set(Status, { value: 3 }));
console.log("e1 =", e1, "hasComponent:", hasComponent(world, e1, Status), "Status.value =", Status.value);

console.log("query(world, [Status]) =", query(world, [Status]));
console.log("Status.value[e0] =", Status.value[e0], "Status.value[e1] =", Status.value[e1]);
