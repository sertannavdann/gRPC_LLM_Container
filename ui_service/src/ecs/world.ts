'use client';

import { World } from 'miniplex';
import type { EntityRecord, CanvasView } from './types';
import { createDirtyTracker } from './dirty';

// ── Reactivity bridge (ported verbatim from the skill blueprint) ───────────
//
// Neither miniplex nor miniplex-react fires on component-VALUE mutation, only
// on add/remove. This module-scope bridge is mandatory boilerplate, not
// trimmable — useSyncExternalStore requires a stable subscribe/getSnapshot
// pair, and it is module-global on purpose so every consumer shares it.

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

// ── The one world ────────────────────────────────────────────────────────
//
// Known deferred gap (09-RESEARCH.md Pitfall 4): ECS-only fields do not
// survive a remove/re-add cycle; CONTEXT.md defers a grace period for that
// to production telemetry — do not build one speculatively here.
//
// Do NOT add ECS "systems" for validation/highlighting/layout (locked
// decision D9-14, spike 004 measured 3x code for zero benefit) — those stay
// as `resolveLifecycle`-style pure functions.

export function createPipelineWorld() {
  const world = new World<EntityRecord>();
  const byId = new Map<string, EntityRecord>();
  const tracker = createDirtyTracker();

  // Choke point 1 of 3 — plan 04/05's sync.ts and mediation.ts MUST call this
  // rather than world.add directly, or dirty tracking silently loses events.
  function add(rec: EntityRecord): EntityRecord {
    const entity = world.add({
      ...rec,
      creds: [...rec.creds],
      flags: [...rec.flags],
    });
    byId.set(rec.id, entity);
    tracker.markDirty(rec.id);
    return entity;
  }

  // Choke point 2 of 3.
  function removeById(id: string) {
    const entity = byId.get(id);
    if (!entity) return;
    world.remove(entity);
    byId.delete(id);
    tracker.markRemoved(id);
  }

  // Choke point 3 of 3.
  function mutate(id: string, patch: Partial<EntityRecord>) {
    const entity = byId.get(id);
    if (!entity) return;
    Object.assign(entity, patch);
    tracker.markDirty(id);
  }

  function views(): CanvasView[] {
    return [...world.entities].map((e) => {
      const { x: _x, y: _y, ...rest } = e;
      return { ...rest, creds: [...e.creds], flags: [...e.flags] };
    });
  }

  function viewOf(id: string): CanvasView | null {
    const entity = byId.get(id);
    if (!entity) return null;
    const { x: _x, y: _y, ...rest } = entity;
    return { ...rest, creds: [...entity.creds], flags: [...entity.flags] };
  }

  function entityCount() {
    return byId.size;
  }

  return { world, byId, tracker, add, removeById, mutate, views, viewOf, entityCount };
}

export const canvasWorld = createPipelineWorld();
