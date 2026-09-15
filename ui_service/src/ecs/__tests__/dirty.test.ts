import { describe, it, expect } from 'vitest';
import { createPipelineWorld } from '../world';
import { createDirtyTracker } from '../dirty';
import { canonicalize, toDelta } from '../verbalize';
import type { CanvasView, EntityRecord } from '../types';

// Deterministic seeded LCG — no Math.random, ported from
// .planning/spikes/006-delta-context-streaming/churn.mjs makeRng().
function makeRng(seed = 1337) {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 0x100000000;
  };
}

const STATUS_POOL = ['running', 'degraded', 'error', 'idle', 'stopped'] as const;

function makeFixture(): EntityRecord[] {
  const fixture: EntityRecord[] = [];
  const kinds: EntityRecord['kind'][] = ['service', 'module', 'adapter', 'stage', 'tool'];
  for (let i = 0; i < 26; i++) {
    const kind = kinds[i % kinds.length];
    fixture.push({
      id: `${kind}-${i}`,
      label: `Entity ${i}`,
      kind,
      status: 'running',
      lifecycle: kind === 'module' ? 'enabled' : null,
      detail: null,
      latency: i % 3 === 0 ? i * 10 : null,
      creds: kind === 'module' && i % 4 === 0 ? [`CRED_${i}`] : [],
      flags: [],
      x: i * 10,
      y: i * 5,
    });
  }
  return fixture;
}

type Op =
  | { op: 'status'; id: string; value: string }
  | { op: 'metrics'; id: string; latency: number }
  | { op: 'remove'; id: string }
  | { op: 'add'; rec: EntityRecord };

// Deterministic 40-tick churn script — port of makeChurnScript's shape,
// hardcoded/seeded so both this test and any future replay stay reproducible.
function makeChurnScript(fixture: EntityRecord[], ticks: number, seed = 1337): Op[][] {
  const rng = makeRng(seed);
  const ids = fixture.map((r) => r.id);
  const removable = fixture.filter((r) => r.kind === 'module').map((r) => r.id);
  const recsById = new Map(fixture.map((r) => [r.id, r]));
  const removed = new Set<string>();
  const script: Op[][] = [];

  for (let t = 0; t < ticks; t++) {
    const ops: Op[] = [];
    const jitters = 2 + Math.floor(rng() * 3);
    for (let j = 0; j < jitters; j++) {
      const id = ids[Math.floor(rng() * ids.length)];
      if (removed.has(id)) continue;
      ops.push({ op: 'metrics', id, latency: Math.round(rng() * 1000) / 10 });
    }
    if (rng() < 0.5) {
      const id = ids[Math.floor(rng() * ids.length)];
      if (!removed.has(id)) {
        ops.push({ op: 'status', id, value: STATUS_POOL[1 + Math.floor(rng() * (STATUS_POOL.length - 1))] });
      }
    }
    if (rng() < 0.1 && removable.length) {
      const id = removable[Math.floor(rng() * removable.length)];
      if (!removed.has(id)) {
        removed.add(id);
        ops.push({ op: 'remove', id });
      }
    }
    if (rng() < 0.1 && removed.size) {
      const id = [...removed][0];
      removed.delete(id);
      ops.push({ op: 'add', rec: recsById.get(id)! });
    }
    script.push(ops);
  }
  return script;
}

describe('dirty tracker: delta mirror-reconstruction exactness', () => {
  it('keeps an LLM-mental-model mirror correct at every invocation across a 40-tick churn session', () => {
    const world = createPipelineWorld();
    const fixture = makeFixture();
    for (const rec of fixture) world.add(rec);

    // LLM mental-model mirror: fed only by full-snapshot views or delta records.
    const mirror = new Map<string, CanvasView>();
    function applyFullToMirror(views: CanvasView[]) {
      mirror.clear();
      for (const v of views) mirror.set(v.id, v);
    }
    function applyDeltaToMirror(delta: { changed: CanvasView[]; removed: string[] }) {
      for (const id of delta.removed) mirror.delete(id);
      for (const v of delta.changed) mirror.set(v.id, v);
    }
    function mirrorEquals(views: CanvasView[]) {
      const a = JSON.stringify(canonicalize(views));
      const b = JSON.stringify(canonicalize([...mirror.values()]));
      return a === b;
    }

    const script = makeChurnScript(fixture, 40, 1337);

    // Invocation 0: baseline full snapshot.
    applyFullToMirror(world.views());
    world.tracker.clearSinceLastInvocation();
    expect(mirrorEquals(world.views())).toBe(true);

    const INVOKE_EVERY = 5;
    let sawNonEmptyRemoved = false;
    let sawNonEmptyChanged = false;

    for (let tick = 0; tick < script.length; tick++) {
      for (const op of script[tick]) {
        if (op.op === 'metrics') world.mutate(op.id, { latency: op.latency });
        else if (op.op === 'status') world.mutate(op.id, { status: op.value as EntityRecord['status'] });
        else if (op.op === 'remove') world.removeById(op.id);
        else if (op.op === 'add') world.add(op.rec);
      }

      if ((tick + 1) % INVOKE_EVERY === 0) {
        const delta = toDelta(
          world.tracker.dirty,
          world.tracker.removedIds,
          world.viewOf,
          world.tracker.version()
        );
        applyDeltaToMirror(delta);

        // The single most important assertion in this suite.
        expect(mirrorEquals(world.views())).toBe(true);

        if (delta.removed.length) sawNonEmptyRemoved = true;
        if (delta.changed.length) sawNonEmptyChanged = true;

        world.tracker.clearSinceLastInvocation();
      }
    }

    // The test cannot pass vacuously.
    expect(sawNonEmptyRemoved).toBe(true);
    expect(sawNonEmptyChanged).toBe(true);
  });

  it('markDirty then markRemoved leaves the id in removedIds only', () => {
    const tracker = createDirtyTracker();
    tracker.markDirty('x');
    tracker.markRemoved('x');
    expect(tracker.dirty.has('x')).toBe(false);
    expect(tracker.removedIds.has('x')).toBe(true);
  });

  it('markRemoved then markDirty leaves the id in dirty only', () => {
    const tracker = createDirtyTracker();
    tracker.markRemoved('y');
    tracker.markDirty('y');
    expect(tracker.removedIds.has('y')).toBe(false);
    expect(tracker.dirty.has('y')).toBe(true);
  });
});
