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
