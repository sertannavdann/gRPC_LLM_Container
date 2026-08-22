// miniplex 2.0 world adapter for spike 005b.
//
// Representation: plain entity objects (miniplex's native grain) — the winning shape
// from spike 003a. Snapshot/restore is HAND-ROLLED here because miniplex ships none:
// - serialize: canonical JSON of entity records (sorted by id)
// - restore: clear + re-add into a fresh world
// A structuredClone-based binary-ish path is also benchmarked for the rewind story.

import { World } from "miniplex";

export function createPipelineWorld() {
  const world = new World();
  const byId = new Map();

  function add(rec) {
    const entity = world.add({
      id: rec.id, label: rec.label, kind: rec.kind, status: rec.status,
      lifecycle: rec.lifecycle, cpu: rec.cpu, mem: rec.mem, x: rec.x, y: rec.y,
      credentials: [...rec.credentials],
    });
    byId.set(rec.id, entity);
    return entity;
  }

  function remove(id) {
    const entity = byId.get(id);
    if (!entity) return;
    world.remove(entity);
    byId.delete(id);
  }

  // Canonical plain view records — for miniplex this is nearly the identity function.
  function views() {
    return [...world.entities].map((e) => ({
      id: e.id, label: e.label, kind: e.kind, status: e.status, lifecycle: e.lifecycle,
      cpu: e.cpu, mem: e.mem, x: e.x, y: e.y, credentials: [...e.credentials],
    }));
  }

  // Hand-rolled snapshot: canonical JSON string (sorted by id for stability).
  function serialize() {
    const sorted = views().sort((a, b) => (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    return JSON.stringify(sorted);
  }

  function deserialize(json) {
    for (const e of [...world.entities]) world.remove(e);
    byId.clear();
    for (const rec of JSON.parse(json)) add(rec);
  }

  // Rewind-style snapshot without stringify, for cost comparison.
  function snapshotClone() {
    return structuredClone(views());
  }

  return { world, byId, add, remove, views, serialize, deserialize, snapshotClone };
}
