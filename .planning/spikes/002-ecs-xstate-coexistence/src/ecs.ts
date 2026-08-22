import { World } from "miniplex";

export type NodeStatus = "idle" | "building" | "validating" | "validated" | "error";

export type PipelineEntity = {
  id: string;
  // --- Mirrored components: written ONLY by the sync system from XState
  // context. Never mutated directly by UI event handlers. ---
  label: string;
  status: NodeStatus;
  position: { x: number; y: number };
  // --- ECS-only components: written ONLY by UI event handlers (hover,
  // local drag offset). XState never knows these exist. The sync system
  // must never overwrite these when it patches mirrored fields. ---
  hovered: boolean;
  dragCount: number;
};

export const world = new World<PipelineEntity>();

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

export function resetWorld() {
  world.clear();
  version = 0;
}
