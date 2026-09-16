import { describe, it, expect } from 'vitest';
import { createActor, fromCallback, fromPromise } from 'xstate';
import {
  pipelinePageMachine,
  pipelineNodeIds,
  STAGE_NODE_IDS,
} from '../pipelinePage';
import type {
  PipelineState,
  ApprovalResult,
  ModuleReview,
  ModuleAuditAttempt,
} from '../../lib/adminClient';

// ── Fixture ──────────────────────────────────────────────────────────────────

function snapshot(moduleIds: string[], serviceNames: string[]): PipelineState {
  const services: PipelineState['services'] = {};
  serviceNames.forEach((name) => {
    services[name] = { name, state: 'running', latency_ms: 10 };
  });

  return {
    services,
    modules: moduleIds.map((id) => ({
      id,
      name: id,
      state: 'running',
    })),
    adapters: [],
    adapters_count: 0,
    tools: [],
    stage_tools: {},
    timestamp: Date.now() / 1000,
  };
}

// ── Stubbed machine (no network/EventSource under vitest node env) ──────────

const fakeApprovalResult: ApprovalResult = {
  status: 'ok',
  module_id: 'test',
  new_status: 'enabled',
};

const fakeReview = {} as ModuleReview;

const testMachine = pipelinePageMachine.provide({
  actors: {
    sseConnection: fromCallback(() => () => {}),
    loadReview: fromPromise(async () => ({
      review: fakeReview,
      audit: [] as ModuleAuditAttempt[],
    })),
    approveAction: fromPromise(async () => fakeApprovalResult),
    rejectAction: fromPromise(async () => fakeApprovalResult),
    approveChange: fromPromise(async () => ({ ok: true, label: 'pre-approve:prop-1' } as { ok: boolean; error?: string; label: string })),
    rejectChange: fromPromise(async () => ({ ok: true, rewound: true } as { ok: boolean; rewound: boolean })),
  },
});

describe('pipelinePageMachine — clearSelectionIfMissing', () => {
  it('keeps the selection when the selected entity is still present', () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'SSE_MESSAGE',
      data: snapshot(['weather/openweather'], []),
    });
    actor.send({ type: 'SELECT_NODE', nodeId: 'module-weather/openweather' });
    actor.send({
      type: 'SSE_MESSAGE',
      data: snapshot(['weather/openweather'], []),
    });

    expect(actor.getSnapshot().context.selectedNodeId).toBe(
      'module-weather/openweather'
    );
    actor.stop();
  });

  it('clears the selection in the same transition the entity disappears', () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'SSE_MESSAGE',
      data: snapshot(['weather/openweather'], []),
    });
    actor.send({ type: 'SELECT_NODE', nodeId: 'module-weather/openweather' });
    actor.send({ type: 'SSE_MESSAGE', data: snapshot([], []) });

    const ctx = actor.getSnapshot().context;
    expect(ctx.selectedNodeId).toBeNull();
    expect(ctx.selectedModuleId).toBeNull();
    expect(ctx.review).toBeNull();
    actor.stop();
  });

  it('clears the selection from the reconnecting substate too', () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'SSE_MESSAGE',
      data: snapshot(['weather/openweather'], []),
    });
    actor.send({ type: 'SELECT_NODE', nodeId: 'module-weather/openweather' });
    actor.send({ type: 'SSE_ERROR' }); // connected -> reconnecting
    actor.send({ type: 'SSE_MESSAGE', data: snapshot([], []) });

    expect(actor.getSnapshot().context.selectedNodeId).toBeNull();
    actor.stop();
  });

  it('keeps a static stage selection across snapshots', () => {
    const actor = createActor(testMachine).start();

    actor.send({ type: 'SELECT_NODE', nodeId: 'stage-tools' });
    actor.send({
      type: 'SSE_MESSAGE',
      data: snapshot(['weather/openweather'], []),
    });

    expect(actor.getSnapshot().context.selectedNodeId).toBe('stage-tools');
    actor.stop();
  });

  it('does not throw on a malformed/error-variant snapshot', () => {
    const actor = createActor(testMachine).start();

    actor.send({ type: 'SELECT_NODE', nodeId: 'stage-tools' });
    expect(() => {
      actor.send({
        type: 'SSE_MESSAGE',
        data: { error: 'boom', timestamp: 1 } as unknown as PipelineState,
      });
    }).not.toThrow();

    expect(actor.getSnapshot().status).toBe('active');
    actor.stop();
  });

  it('pipelineNodeIds returns exactly the expected id set including stage ids', () => {
    const data = snapshot(['weather/openweather'], ['orchestrator']);
    const ids = pipelineNodeIds(data);

    expect(ids).toEqual(
      new Set([
        ...STAGE_NODE_IDS,
        'svc-orchestrator',
        'module-weather/openweather',
      ])
    );
  });
});

describe('pipelinePageMachine — canvasOpApproval branch', () => {
  it('CANVAS_PROPOSAL moves reviewPanel to open and sets canvasProposalId', () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'CANVAS_PROPOSAL',
      proposalId: 'prop-1',
      nodeId: 'module-weather/openweather',
    });

    const snap = actor.getSnapshot();
    expect(snap.matches({ reviewPanel: 'open' })).toBe(true);
    expect(snap.context.canvasProposalId).toBe('prop-1');
    expect(snap.context.selectedNodeId).toBe('module-weather/openweather');
    actor.stop();
  });

  it('APPROVE_CHANGE from open reaches approvingChange and returns to closed', async () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'CANVAS_PROPOSAL',
      proposalId: 'prop-1',
      nodeId: 'module-weather/openweather',
    });
    actor.send({ type: 'APPROVE_CHANGE' });
    expect(actor.getSnapshot().matches({ reviewPanel: 'approvingChange' })).toBe(true);

    await new Promise((r) => setTimeout(r, 0));

    expect(actor.getSnapshot().matches({ reviewPanel: 'closed' })).toBe(true);
    actor.stop();
  });

  it('REJECT_CHANGE with a rewound result sets canvasRewound === true', async () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'CANVAS_PROPOSAL',
      proposalId: 'prop-1',
      nodeId: 'module-weather/openweather',
    });
    actor.send({ type: 'REJECT_CHANGE' });

    await new Promise((r) => setTimeout(r, 0));

    expect(actor.getSnapshot().context.canvasRewound).toBe(true);
    actor.stop();
  });

  it('an SSE_MESSAGE omitting the proposal target node clears canvasProposalId', () => {
    const actor = createActor(testMachine).start();

    actor.send({
      type: 'CANVAS_PROPOSAL',
      proposalId: 'prop-1',
      nodeId: 'module-weather/openweather',
    });
    actor.send({ type: 'SSE_MESSAGE', data: snapshot([], []) });

    expect(actor.getSnapshot().context.canvasProposalId).toBeNull();
    actor.stop();
  });

  it('a stubbed actor rejection routes to the error substate with actionError set', async () => {
    const failingMachine = pipelinePageMachine.provide({
      actors: {
        sseConnection: fromCallback(() => () => {}),
        loadReview: fromPromise(async () => ({
          review: fakeReview,
          audit: [] as ModuleAuditAttempt[],
        })),
        approveAction: fromPromise(async () => fakeApprovalResult),
        rejectAction: fromPromise(async () => fakeApprovalResult),
        approveChange: fromPromise((): Promise<{ ok: boolean; error?: string; label: string }> => {
          throw new Error('Proposal is invalidated, not staged');
        }),
        rejectChange: fromPromise(async () => ({ ok: true, rewound: true } as { ok: boolean; rewound: boolean })),
      },
    });

    const actor = createActor(failingMachine).start();

    actor.send({
      type: 'CANVAS_PROPOSAL',
      proposalId: 'prop-1',
      nodeId: 'module-weather/openweather',
    });
    actor.send({ type: 'APPROVE_CHANGE' });

    await new Promise((r) => setTimeout(r, 0));

    const snap = actor.getSnapshot();
    expect(snap.matches({ reviewPanel: 'error' })).toBe(true);
    expect(snap.context.actionError).toBe('Proposal is invalidated, not staged');
    actor.stop();
  });
});
