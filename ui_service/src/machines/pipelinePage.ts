/**
 * Pipeline Page Statechart (XState v5)
 *
 * Parallel state machine managing the pipeline page with three independent regions:
 * 1. connection: SSE connection lifecycle (connecting -> connected -> reconnecting)
 * 2. selection: currently-selected graph node
 * 3. reviewPanel: module approval review panel (closed -> loading -> open -> approving/rejecting -> ...)
 *
 * The `sseConnection` actor (fromCallback) wraps the existing `connectPipelineSSE()`
 * EventSource helper and is invoked at the `connection` region level so it stays
 * alive across `connecting -> connected -> reconnecting` transitions — native
 * EventSource already auto-retries, so the actor is not torn down/recreated per
 * transition. Its cleanup function closes the EventSource on region exit (D-14,
 * T-08-31 leak mitigation).
 *
 * Academic anchor: Harel Statecharts with parallel (orthogonal) regions —
 * mirrors `monitoringPage.ts`/`financePage.ts` precedent.
 */

import { setup, fromCallback, fromPromise, assign } from 'xstate';
import {
  adminApi,
  connectPipelineSSE,
  type PipelineState,
  type ModuleReview,
  type ModuleAuditAttempt,
} from '../lib/adminClient';

// ── Context & Events ─────────────────────────────────────────────────────────

export interface PipelinePageContext {
  pipeline: PipelineState | null;
  lastUpdate: number;
  selectedNodeId: string | null;
  selectedModuleId: string | null;
  review: ModuleReview | null;
  audit: ModuleAuditAttempt[];
  actionError: string | null;
}

export type PipelinePageEvent =
  | { type: 'SSE_MESSAGE'; data: PipelineState }
  | { type: 'SSE_ERROR' }
  | { type: 'SELECT_NODE'; nodeId: string; moduleId?: string }
  | { type: 'CLOSE_PANEL' }
  | { type: 'APPROVE' }
  | { type: 'REJECT'; feedback?: string }
  | { type: 'RETRY' };

// ── Helpers ──────────────────────────────────────────────────────────────────

/** Splits a `category/platform` module id into its two path segments. */
function splitModuleId(moduleId: string): [category: string, platform: string] {
  const [category, platform] = moduleId.split('/');
  return [category, platform];
}

// ── Invoked Actors ───────────────────────────────────────────────────────────

const loadReview = fromPromise(
  async ({
    input,
  }: {
    input: { moduleId: string | null };
  }): Promise<{ review: ModuleReview; audit: ModuleAuditAttempt[] }> => {
    if (!input.moduleId) {
      throw new Error('No module selected for review');
    }
    const [category, platform] = splitModuleId(input.moduleId);
    const [review, auditLog] = await Promise.all([
      adminApi.getModuleReview(category, platform),
      adminApi.getModuleAudit(category, platform),
    ]);
    return { review, audit: auditLog.attempts };
  }
);

const approveAction = fromPromise(
  async ({ input }: { input: { moduleId: string | null } }) => {
    if (!input.moduleId) {
      throw new Error('No module selected to approve');
    }
    const [category, platform] = splitModuleId(input.moduleId);
    return adminApi.approveModule(category, platform);
  }
);

const rejectAction = fromPromise(
  async ({
    input,
  }: {
    input: { moduleId: string | null; feedback?: string };
  }) => {
    if (!input.moduleId) {
      throw new Error('No module selected to reject');
    }
    const [category, platform] = splitModuleId(input.moduleId);
    return adminApi.rejectModule(category, platform, input.feedback);
  }
);

// ── XState v5 Machine Setup ─────────────────────────────────────────────────

export const pipelinePageMachine = setup({
  types: {
    context: {} as PipelinePageContext,
    events: {} as PipelinePageEvent,
  },

  actors: {
    sseConnection: fromCallback<PipelinePageEvent>(({ sendBack }) => {
      const es = connectPipelineSSE(
        (state) => sendBack({ type: 'SSE_MESSAGE', data: state }),
        () => sendBack({ type: 'SSE_ERROR' })
      );
      return () => es.close(); // cleanup on region exit — mandatory (T-08-31)
    }),
    loadReview,
    approveAction,
    rejectAction,
  },

  guards: {
    hasModuleId: ({ event }) =>
      event.type === 'SELECT_NODE' && !!event.moduleId,
  },

  actions: {
    updatePipeline: assign(({ event }) => {
      if (event.type !== 'SSE_MESSAGE') return {};
      return { pipeline: event.data, lastUpdate: Date.now() };
    }),

    setSelection: assign(({ event }) => {
      if (event.type !== 'SELECT_NODE') return {};
      return {
        selectedNodeId: event.nodeId,
        selectedModuleId: event.moduleId ?? null,
      };
    }),

    clearSelection: assign(() => ({
      selectedNodeId: null,
      selectedModuleId: null,
      review: null,
      audit: [],
      actionError: null,
    })),

    storeReview: assign(({ event }) => {
      const doneEvent = event as unknown as {
        output?: { review: ModuleReview; audit: ModuleAuditAttempt[] };
      };
      if (!doneEvent.output) return {};
      return { review: doneEvent.output.review, audit: doneEvent.output.audit };
    }),

    storeActionError: assign(({ event }) => {
      const errorEvent = event as unknown as { error?: unknown };
      const message =
        errorEvent.error instanceof Error
          ? errorEvent.error.message
          : 'Action failed';
      return { actionError: message };
    }),
  },
}).createMachine({
  id: 'pipelinePage',
  type: 'parallel',
  context: {
    pipeline: null,
    lastUpdate: 0,
    selectedNodeId: null,
    selectedModuleId: null,
    review: null,
    audit: [],
    actionError: null,
  },

  states: {
    // Region 1: SSE connection lifecycle
    connection: {
      initial: 'connecting',
      // Invoked at the region level so the EventSource survives
      // connecting -> connected -> reconnecting transitions.
      invoke: {
        src: 'sseConnection',
      },
      states: {
        connecting: {
          on: {
            SSE_MESSAGE: { target: 'connected', actions: 'updatePipeline' },
          },
        },
        connected: {
          on: {
            SSE_MESSAGE: { actions: 'updatePipeline' },
            SSE_ERROR: 'reconnecting',
          },
        },
        reconnecting: {
          on: {
            SSE_MESSAGE: { target: 'connected', actions: 'updatePipeline' },
          },
        },
      },
    },

    // Region 2: Selected graph node
    selection: {
      initial: 'none',
      states: {
        none: {
          on: {
            SELECT_NODE: { target: 'selected', actions: 'setSelection' },
          },
        },
        selected: {
          on: {
            SELECT_NODE: { actions: 'setSelection' },
            CLOSE_PANEL: { target: 'none', actions: 'clearSelection' },
          },
        },
      },
    },

    // Region 3: Module approval review panel
    reviewPanel: {
      initial: 'closed',
      states: {
        closed: {
          on: {
            SELECT_NODE: {
              target: 'loading',
              guard: 'hasModuleId',
            },
          },
        },
        loading: {
          invoke: {
            src: 'loadReview',
            input: ({ context }) => ({ moduleId: context.selectedModuleId }),
            onDone: { target: 'open', actions: 'storeReview' },
            onError: { target: 'error', actions: 'storeActionError' },
          },
        },
        open: {
          on: {
            APPROVE: 'approving',
            REJECT: 'rejecting',
            CLOSE_PANEL: 'closed',
          },
        },
        approving: {
          invoke: {
            src: 'approveAction',
            input: ({ context }) => ({ moduleId: context.selectedModuleId }),
            onDone: { target: 'closed', actions: 'clearSelection' },
            onError: { target: 'error', actions: 'storeActionError' },
          },
        },
        rejecting: {
          invoke: {
            src: 'rejectAction',
            input: ({ context, event }) => ({
              moduleId: context.selectedModuleId,
              feedback: event.type === 'REJECT' ? event.feedback : undefined,
            }),
            onDone: { target: 'closed', actions: 'clearSelection' },
            onError: { target: 'error', actions: 'storeActionError' },
          },
        },
        error: {
          on: {
            RETRY: 'loading',
            CLOSE_PANEL: 'closed',
          },
        },
      },
    },
  },
});
