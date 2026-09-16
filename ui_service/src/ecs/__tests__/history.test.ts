import { describe, it, expect } from 'vitest';
import { createPipelineWorld } from '../world';
import { createMediation } from '../mediation';
import { createHistory, restoreSnapshot, replayEvents } from '../history';
import { canonicalize } from '../verbalize';
import type { EntityRecord } from '../types';

// Fresh world + mediation + history per test (never the production
// module-level singleton instances) — matches 09-04's harness convention.
function setup(capacity = 20) {
  const w = createPipelineWorld();
  const m = createMediation(w);
  const h = createHistory(w, m, { capacity });
  return { w, m, h };
}

function seedModule(w: ReturnType<typeof createPipelineWorld>, overrides: Partial<EntityRecord> = {}): EntityRecord {
  const rec: EntityRecord = {
    id: 'module-x',
    label: 'Module X',
    kind: 'module',
    status: 'running',
    lifecycle: 'enabled',
    detail: null,
    latency: null,
    creds: [],
    flags: [],
    x: 0,
    y: 0,
    ...overrides,
  };
  w.add(rec);
  return rec;
}

function seedService(w: ReturnType<typeof createPipelineWorld>, overrides: Partial<EntityRecord> = {}): EntityRecord {
  const rec: EntityRecord = {
    id: 'svc-llm',
    label: 'LLM Service',
    kind: 'service',
    status: 'running',
    lifecycle: null,
    detail: null,
    latency: 10,
    creds: [],
    flags: [],
    x: 0,
    y: 0,
    ...overrides,
  };
  w.add(rec);
  return rec;
}

function snap(w: ReturnType<typeof createPipelineWorld>): string {
  return JSON.stringify(canonicalize(w.views()));
}

function fullSnap(w: ReturnType<typeof createPipelineWorld>): string {
  return JSON.stringify(canonicalize([...w.world.entities]));
}

describe('history — no duplication after drift (spike 005a failure mode)', () => {
  it('restoreSnapshot over a drifted world reproduces the exact pre-drift state', () => {
    const { w } = setup();
    seedService(w);
    seedModule(w);
    const originalCount = w.entityCount();
    const before = fullSnap(w);
    const snapshotJson = JSON.stringify(canonicalize([...w.world.entities] as EntityRecord[]));

    // Drift: add two, remove one, mutate one.
    w.add({
      id: 'module-y',
      label: 'Module Y',
      kind: 'module',
      status: 'running',
      lifecycle: 'enabled',
      detail: null,
      latency: null,
      creds: [],
      flags: [],
      x: 5,
      y: 5,
    });
    w.add({
      id: 'module-z',
      label: 'Module Z',
      kind: 'module',
      status: 'running',
      lifecycle: 'enabled',
      detail: null,
      latency: null,
      creds: [],
      flags: [],
      x: 6,
      y: 6,
    });
    w.removeById('module-x');
    w.mutate('svc-llm', { status: 'error' });

    restoreSnapshot(w, snapshotJson);

    expect(w.entityCount()).toBe(originalCount);
    const ids = w.views().map((v) => v.id);
    expect(new Set(ids).size).toBe(w.views().length);
    expect(fullSnap(w)).toBe(before);
  });
});

describe('history — restore marks everything dirty', () => {
  it('every restored id lands in tracker.dirty and removedIds is empty', () => {
    const { w } = setup();
    seedService(w);
    seedModule(w);
    const records = [...w.world.entities] as EntityRecord[];
    const json = JSON.stringify(canonicalize(records));

    w.tracker.clearSinceLastInvocation();
    restoreSnapshot(w, json);

    for (const rec of records) {
      expect(w.tracker.dirty.has(rec.id)).toBe(true);
    }
    expect(w.tracker.removedIds.size).toBe(0);
  });
});

describe('history — UI-only fields survive rewind (D9-13)', () => {
  it('x/y are exactly the snapshotted values after restore', () => {
    const { w } = setup();
    seedModule(w, { x: 42, y: 99 });
    const records = [...w.world.entities] as EntityRecord[];
    const json = JSON.stringify(canonicalize(records));

    w.mutate('module-x', { x: 0, y: 0 });
    w.add({
      id: 'module-extra',
      label: 'Extra',
      kind: 'module',
      status: 'running',
      lifecycle: 'enabled',
      detail: null,
      latency: null,
      creds: [],
      flags: [],
      x: 1,
      y: 1,
    });

    restoreSnapshot(w, json);
    const restored = w.byId.get('module-x')!;
    expect(restored.x).toBe(42);
    expect(restored.y).toBe(99);
  });
});

describe('history — reject-with-rewind', () => {
  it('rewinds an approved proposal and reports rewound: true', () => {
    const { w, m, h } = setup();
    seedModule(w, { status: 'running' });

    const propose = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    expect(propose.accepted).toBe(true);
    h.approveWithHistory(propose.proposalId!);
    expect(w.byId.get('module-x')!.status).toBe('stopped');

    const result = h.rejectWithRewind(propose.proposalId!);
    expect(result.ok).toBe(true);
    expect(result.rewound).toBe(true);
    expect(w.byId.get('module-x')!.status).toBe('running');
  });

  it('a staged-only proposal reports rewound: false and leaves the world unchanged', () => {
    const { w, m, h } = setup();
    seedModule(w, { status: 'running' });
    const before = fullSnap(w);

    const propose = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    expect(propose.accepted).toBe(true);

    const result = h.rejectWithRewind(propose.proposalId!);
    expect(result.ok).toBe(true);
    expect(result.rewound).toBe(false);
    expect(fullSnap(w)).toBe(before);
  });
});

describe('history — replay determinism', () => {
  it('replaying the same event slice into a fresh world reproduces the byte-identical serialization', () => {
    const { w, m, h } = setup();

    const fixture1: EntityRecord[] = [seedRecord('svc-llm', 'service', 'running')];
    syncInto(w, m, fixture1);
    h.recordSync(fixture1);

    const p1 = m.propose([{ op: 'set_status', id: 'svc-llm', value: 'degraded' }]);
    h.approveWithHistory(p1.proposalId!);

    const fixture2: EntityRecord[] = [
      { ...fixture1[0], status: 'degraded' },
      seedRecord('module-x', 'module', 'running'),
    ];
    syncInto(w, m, fixture2);
    h.recordSync(fixture2);

    const fixture3: EntityRecord[] = [...fixture2];
    syncInto(w, m, fixture3);
    h.recordSync(fixture3);

    const finalSnap = fullSnap(w);
    const events = h.log.slice();

    const w2 = createPipelineWorld();
    const m2 = createMediation(w2);
    replayEvents(w2, m2, events);

    expect(fullSnap(w2)).toBe(finalSnap);
  });
});

describe('history — replay divergence is loud', () => {
  it('throws with "replay diverged" when an approve event targets a missing entity', () => {
    const w2 = createPipelineWorld();
    const m2 = createMediation(w2);
    expect(() =>
      replayEvents(w2, m2, [
        { seq: 0, type: 'approve', payload: [{ op: 'set_status', id: 'does-not-exist', value: 'running' }] },
      ])
    ).toThrow(/replay diverged/);
  });
});

describe('history — ring bounding + checkpoint', () => {
  it('bounds the ring at capacity and stops the log from growing unbounded', () => {
    const capacity = 5;
    const { w, h } = setup(capacity);

    for (let i = 0; i < capacity + 5; i++) {
      h.recordSync([seedRecord(`module-${i}`, 'module', 'running')]);
    }

    expect(h.ring.size()).toBe(capacity);
    expect(h.log.length()).toBeLessThanOrEqual(capacity);
  });
});

describe('history — undo/redo round trip', () => {
  it('undo then redo returns to the byte-identical newest serialization', () => {
    const { w, m, h } = setup();

    const fixture: EntityRecord[] = [seedRecord('svc-llm', 'service', 'running')];
    syncInto(w, m, fixture);
    h.recordSync(fixture);

    const p1 = m.propose([{ op: 'set_status', id: 'svc-llm', value: 'degraded' }]);
    h.approveWithHistory(p1.proposalId!);
    h.recordSync([{ ...w.byId.get('svc-llm')! } as EntityRecord]);

    const newest = fullSnap(w);

    expect(h.canUndo()).toBe(true);
    const undoResult = h.undo();
    expect(undoResult.ok).toBe(true);

    const redoResult = h.redo();
    expect(redoResult.ok).toBe(true);
    expect(fullSnap(w)).toBe(newest);

    // Walk to the oldest ring entry: canUndo eventually reports false.
    while (h.canUndo()) h.undo();
    expect(h.canUndo()).toBe(false);

    // Walk back to the newest: canRedo eventually reports false.
    while (h.canRedo()) h.redo();
    expect(h.canRedo()).toBe(false);
  });
});

// ── local helpers ──────────────────────────────────────────────────────────

function seedRecord(id: string, kind: EntityRecord['kind'], status: EntityRecord['status']): EntityRecord {
  return {
    id,
    label: id,
    kind,
    status,
    lifecycle: null,
    detail: null,
    latency: null,
    creds: [],
    flags: [],
    x: 0,
    y: 0,
  };
}

function syncInto(w: ReturnType<typeof createPipelineWorld>, m: ReturnType<typeof createMediation>, records: EntityRecord[]) {
  const incoming = new Set(records.map((r) => r.id));
  for (const entity of [...w.world.entities]) {
    if (!incoming.has(entity.id)) w.removeById(entity.id);
  }
  for (const rec of records) {
    if (w.byId.has(rec.id)) {
      w.mutate(rec.id, rec);
    } else {
      w.add(rec);
    }
  }
  m.revalidateStagedProposals();
}
