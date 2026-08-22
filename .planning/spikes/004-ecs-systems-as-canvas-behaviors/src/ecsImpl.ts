// --- Implementation A: ECS + a "system" ---
// A world of entities carrying mirrored topology data plus a `highlighted`
// component, and a `highlightSystem` that recomputes it from a hovered id.
import { World } from "miniplex";
import { TOPOLOGY } from "./topology";

export type EcsEntity = {
  id: string;
  label: string;
  position: { x: number; y: number };
  connections: string[];
  highlighted: boolean;
};

export const world = new World<EcsEntity>();
for (const n of TOPOLOGY) {
  world.add({ id: n.id, label: n.label, position: n.position, connections: n.connections, highlighted: false });
}

type Listener = () => void;
const listeners = new Set<Listener>();
let version = 0;
export function touch() {
  version++;
  listeners.forEach((l) => l());
}
export function subscribeWorld(listener: Listener) {
  listeners.add(listener);
  return () => listeners.delete(listener);
}
export function getWorldVersion() {
  return version;
}
export function byId(id: string) {
  return world.entities.find((e) => e.id === id);
}

/** The "system": iterates the world, derives `highlighted` for every
 * entity from the current hover target and the connection graph. */
export function highlightSystem(hoveredId: string | null) {
  const hovered = hoveredId ? byId(hoveredId) : undefined;
  const neighborIds = new Set<string>();
  if (hovered) {
    neighborIds.add(hovered.id);
    for (const target of hovered.connections) neighborIds.add(target);
    for (const e of world.entities) {
      if (e.connections.includes(hovered.id)) neighborIds.add(e.id);
    }
  }
  for (const e of world.entities) {
    e.highlighted = neighborIds.has(e.id);
  }
  touch();
}
