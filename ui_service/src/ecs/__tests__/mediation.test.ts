import { describe, it, expect } from 'vitest';
import { createPipelineWorld } from '../world';
import { createMediation } from '../mediation';
import { syncRecords } from '../sync';
import { toCompactDsl } from '../verbalize';
import type { EntityRecord } from '../types';

// Fresh world + mediation per test (never the production module-level
// singleton instances) — 09-04-PLAN.md's explicit requirement.
function setup() {
  const w = createPipelineWorld();
  const m = createMediation(w);
  return { w, m };
}

function seedModule(w: ReturnType<typeof createPipelineWorld>, overrides: Partial<EntityRecord> = {}) {
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

function seedService(w: ReturnType<typeof createPipelineWorld>, overrides: Partial<EntityRecord> = {}) {
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

describe('mediation — schema validation (V5 / T-09-05)', () => {
  it('rejects a set_status op with an invalid enum value', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'set_status', id: 'module-x', value: 'not-a-status' } as never]);
    expect(r.accepted).toBe(false);
    expect(r.errors?.[0]).toMatch(/value/);
  });

  it('rejects an unknown op name', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'explode_world' } as never]);
    expect(r.accepted).toBe(false);
  });

  it('rejects an op with an extra unknown field (.strict())', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([
      { op: 'set_status', id: 'module-x', value: 'running', extra: 'nope' } as never,
    ]);
    expect(r.accepted).toBe(false);
  });

  it('rejects a move op with a string x', () => {
    const { w, m } = setup();
    seedService(w);
    const r = m.propose([{ op: 'move', id: 'svc-llm', x: 'left', y: 10 } as never]);
    expect(r.accepted).toBe(false);
  });
});

describe('mediation — ownership policy (V4 / T-09-01)', () => {
  it('refuses set_credentials on a service-kind entity with an ownership-policy message', () => {
    const { w, m } = setup();
    seedService(w);
    const r = m.propose([{ op: 'set_credentials', id: 'svc-llm', list: ['X'] }]);
    expect(r.accepted).toBe(false);
    expect(r.errors?.[0]).toMatch(/ownership policy/);
  });

  it('refuses remove_module targeting a service id', () => {
    const { w, m } = setup();
    seedService(w);
    const r = m.propose([{ op: 'remove_module', id: 'svc-llm' }]);
    expect(r.accepted).toBe(false);
    expect(r.errors?.[0]).toMatch(/ownership policy/);
  });

  it('accepts the same set_credentials op targeting a module entity', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'set_credentials', id: 'module-x', list: ['X'] }]);
    expect(r.accepted).toBe(true);
  });

  it('refuses approval of a forged proposal whose target kind changed after staging', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'set_credentials', id: 'module-x', list: ['X'] }]);
    expect(r.accepted).toBe(true);
    const proposalId = r.proposalId!;

    // Forge: mutate the target's kind in the live world directly (simulating
    // a re-classification that should never let the staged proposal through).
    const entity = w.byId.get('module-x')!;
    entity.kind = 'service';

    const a = m.approve(proposalId);
    expect(a.ok).toBe(false);
    expect(m.getProposal(proposalId)?.status).toBe('invalidated');
  });
});

describe('mediation — re-validation point 2 (T-09-02, via syncRecords)', () => {
  it('invalidates a staged proposal when the target is missing from the next sync', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    expect(r.accepted).toBe(true);
    const proposalId = r.proposalId!;

    // Sync with a record set that OMITS module-x — genuine removal.
    syncRecords(w, m, []);

    const p = m.getProposal(proposalId);
    expect(p?.status).toBe('invalidated');
    expect(p?.reason).toMatch(/does not exist/);
  });
});

describe('mediation — re-validation point 3, non-sync race (T-09-02, spike 007 T5)', () => {
  it('refuses approve() when the target was removed directly without a sync, and does not mutate the world', () => {
    const { w, m } = setup();
    seedModule(w);
    const r = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    expect(r.accepted).toBe(true);
    const proposalId = r.proposalId!;

    w.removeById('module-x');

    const a = m.approve(proposalId);
    expect(a.ok).toBe(false);
    expect(w.byId.has('module-x')).toBe(false);
    expect(w.entityCount()).toBe(0);
  });
});

describe('mediation — preview purity (D9-08)', () => {
  it('previewViews overlays the staged change without mutating the live world', () => {
    const { w, m } = setup();
    seedModule(w);
    const baseline = toCompactDsl(w.views());

    const r = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    const proposalId = r.proposalId!;

    const preview = m.previewViews(proposalId);
    const previewed = preview.find((v) => v.id === 'module-x');
    expect(previewed?.status).toBe('stopped');

    expect(toCompactDsl(w.views())).toBe(baseline);
  });
});

describe('mediation — approve applies through choke points', () => {
  it('marks the target dirty after approval so deltas and the React Flow patch observe it', () => {
    const { w, m } = setup();
    seedModule(w);
    w.tracker.clearSinceLastInvocation();

    const r = m.propose([{ op: 'set_status', id: 'module-x', value: 'stopped' }]);
    const a = m.approve(r.proposalId!);

    expect(a.ok).toBe(true);
    expect(w.tracker.dirty.has('module-x')).toBe(true);
    expect(w.byId.get('module-x')?.status).toBe('stopped');
  });
});

describe('sync — mirrored-fields-only (never overwrites position)', () => {
  it('leaves x/y unchanged while updating mirrored fields like status', () => {
    const { w, m } = setup();
    seedModule(w, { x: 42, y: 99 });

    const incoming: EntityRecord = {
      id: 'module-x',
      label: 'Module X',
      kind: 'module',
      status: 'stopped',
      lifecycle: 'enabled',
      detail: null,
      latency: null,
      creds: [],
      flags: [],
      x: 1000,
      y: 2000,
    };

    syncRecords(w, m, [incoming]);

    const entity = w.byId.get('module-x')!;
    expect(entity.x).toBe(42);
    expect(entity.y).toBe(99);
    expect(entity.status).toBe('stopped');
  });
});
