import { describe, it, expect } from 'vitest';
import { createPipelineWorld } from '../world';
import { createMediation } from '../mediation';
import { proposalAnnotations, createPendingConfirmations } from '../preview';
import type { EntityRecord } from '../types';

// Fresh world + mediation per test — never the production module-level
// singleton instances (matches 09-04's mediation.test.ts convention).
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

describe('proposalAnnotations — pure proposal-to-visual derivation', () => {
  it('a staged set_status proposal produces exactly one field annotation with the exact delta line', () => {
    const { w, m } = setup();
    seedModule(w);
    const { proposalId } = m.propose([{ op: 'set_status', id: 'module-x', value: 'disabled' }]);
    const annotations = proposalAnnotations(m.proposals);
    expect(annotations.size).toBe(1);
    const a = annotations.get('module-x');
    expect(a).toBeDefined();
    expect(a?.proposalId).toBe(proposalId);
    expect(a?.kind).toBe('field');
    expect(a?.deltaLines).toEqual(['status → disabled']);
  });

  it('a staged add_module produces a ghost annotation keyed on the new module id and no annotation on existing ids', () => {
    const { w, m } = setup();
    seedModule(w);
    m.propose([
      {
        op: 'add_module',
        rec: { id: 'module-new', label: 'New Module', status: 'unknown', lifecycle: null },
      },
    ]);
    const annotations = proposalAnnotations(m.proposals);
    expect(annotations.size).toBe(1);
    const a = annotations.get('module-new');
    expect(a?.kind).toBe('ghost');
    expect(a?.deltaLines).toEqual([]);
    expect(annotations.has('module-x')).toBe(false);
  });

  it('a staged remove_module produces a removal annotation', () => {
    const { w, m } = setup();
    seedModule(w);
    m.propose([{ op: 'remove_module', id: 'module-x' }]);
    const annotations = proposalAnnotations(m.proposals);
    const a = annotations.get('module-x');
    expect(a?.kind).toBe('removal');
  });

  it('after approve(), the annotation disappears — approved proposals are live state, not preview', () => {
    const { w, m } = setup();
    seedModule(w);
    const { proposalId } = m.propose([{ op: 'set_status', id: 'module-x', value: 'disabled' }]);
    expect(proposalAnnotations(m.proposals).has('module-x')).toBe(true);
    m.approve(proposalId!);
    expect(proposalAnnotations(m.proposals).has('module-x')).toBe(false);
  });

  it('after revalidateStagedProposals() invalidates a proposal, its annotation disappears', () => {
    const { w, m } = setup();
    seedModule(w);
    m.propose([{ op: 'set_status', id: 'module-x', value: 'disabled' }]);
    expect(proposalAnnotations(m.proposals).size).toBe(1);
    w.removeById('module-x'); // target vanishes — the referential check should now fail
    m.revalidateStagedProposals();
    expect(proposalAnnotations(m.proposals).size).toBe(0);
  });

  it('set_credentials delta lines contain no credential name from the op list — a count only (T-09-06)', () => {
    const { w, m } = setup();
    seedModule(w);
    m.propose([{ op: 'set_credentials', id: 'module-x', list: ['SECRET_API_KEY', 'DB_PASSWORD'] }]);
    const a = proposalAnnotations(m.proposals).get('module-x');
    expect(a?.deltaLines).toEqual(['credentials → 2 items']);
    for (const line of a?.deltaLines ?? []) {
      expect(line).not.toMatch(/SECRET_API_KEY/);
      expect(line).not.toMatch(/DB_PASSWORD/);
    }
  });

  it('never reads or writes the world — proposalAnnotations is provably non-mutating (grep-gated too)', () => {
    const { w, m } = setup();
    const before = seedModule(w);
    m.propose([{ op: 'set_status', id: 'module-x', value: 'disabled' }]);
    proposalAnnotations(m.proposals);
    const after = w.byId.get('module-x');
    expect(after?.status).toBe(before.status); // unchanged: still 'running', not 'disabled'
  });
});

describe('createPendingConfirmations — optimistic-add grace registry (T-09-03)', () => {
  it('mark then resolve leaves pendingIds() empty', () => {
    const pending = createPendingConfirmations();
    pending.mark('module-new');
    expect(pending.pendingIds()).toEqual(['module-new']);
    pending.resolve('module-new');
    expect(pending.pendingIds()).toEqual([]);
  });

  it('mark then expired(now + 4001) returns the id', () => {
    const pending = createPendingConfirmations();
    const now = 1_000_000;
    // Fake the mark time via Date.now() is avoided per the plan's no-fake-timers
    // instruction — instead we mark, then compute expiry relative to a captured
    // real Date.now() call, verifying only the boundary arithmetic contract.
    const markedAt = Date.now();
    pending.mark('module-new');
    void now;
    expect(pending.expired(markedAt + 4001)).toEqual(['module-new']);
  });

  it('expired(now + 3999) does not return the id', () => {
    const pending = createPendingConfirmations();
    const markedAt = Date.now();
    pending.mark('module-new');
    expect(pending.expired(markedAt + 3999)).toEqual([]);
  });

  it('respects a custom graceMs option', () => {
    const pending = createPendingConfirmations({ graceMs: 1000 });
    const markedAt = Date.now();
    pending.mark('module-new');
    expect(pending.expired(markedAt + 1001)).toEqual(['module-new']);
    expect(pending.expired(markedAt + 999)).toEqual([]);
  });
});
