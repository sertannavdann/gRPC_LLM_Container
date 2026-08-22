import { World } from "miniplex";

export type NodeStatus = "idle" | "building" | "validating" | "validated" | "error";

export type PipelineEntity = {
  id: string;
  label: string;
  kind: "service" | "module" | "stage";
  position: { x: number; y: number };
  status: NodeStatus;
  connections: string[]; // target entity ids
  lastTouchedBy: "seed" | "chaos" | "drag";
  updateCount: number;
};

export const world = new World<PipelineEntity>();

const STATUSES: NodeStatus[] = ["idle", "building", "validating", "validated", "error"];

export function seed() {
  const services = world.add({
    id: "orchestrator",
    label: "Orchestrator",
    kind: "service",
    position: { x: 0, y: 0 },
    status: "idle",
    connections: ["dashboard", "sandbox"],
    lastTouchedBy: "seed",
    updateCount: 0,
  });
  world.add({
    id: "dashboard",
    label: "Dashboard",
    kind: "service",
    position: { x: 280, y: -120 },
    status: "idle",
    connections: [],
    lastTouchedBy: "seed",
    updateCount: 0,
  });
  world.add({
    id: "sandbox",
    label: "Sandbox",
    kind: "service",
    position: { x: 280, y: 120 },
    status: "idle",
    connections: [],
    lastTouchedBy: "seed",
    updateCount: 0,
  });
  for (let i = 0; i < 5; i++) {
    world.add({
      id: `module-${i}`,
      label: `module-${i}`,
      kind: "module",
      position: { x: 560, y: -200 + i * 100 },
      status: "idle",
      connections: ["sandbox"],
      lastTouchedBy: "seed",
      updateCount: 0,
    });
  }
  return services;
}

export function byId(id: string) {
  return world.entities.find((e) => e.id === id);
}

// --- Reactivity bridge -----------------------------------------------------
// miniplex tracks entity ADD/REMOVE reactively but does NOT track component
// VALUE mutations. Any system that mutates a component must call touch() so
// subscribers (React) know a re-render is warranted. This is the crux of
// what this spike is testing: is a manual version-counter bridge enough to
// keep React Flow's canvas in sync without fighting its own drag state?
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

// --- Chaos system ------------------------------------------------------
// Simulates the SSE pipeline-state stream (dashboard_service/pipeline_stream.py)
// pushing live status updates every ~2s in production. Runs faster here to
// stress-test render sync under load.
let chaosTimer: ReturnType<typeof setInterval> | null = null;

export function startChaos(intervalMs: number, excludeId: string | null) {
  stopChaos();
  chaosTimer = setInterval(() => {
    const candidates = world.entities.filter((e) => e.id !== excludeId);
    if (candidates.length === 0) return;
    const target = candidates[Math.floor(Math.random() * candidates.length)];
    target.status = STATUSES[Math.floor(Math.random() * STATUSES.length)];
    target.lastTouchedBy = "chaos";
    target.updateCount++;
    touch();
  }, intervalMs);
}

export function stopChaos() {
  if (chaosTimer) clearInterval(chaosTimer);
  chaosTimer = null;
}
