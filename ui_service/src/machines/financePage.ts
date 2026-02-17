/**
 * Finance Page Statechart (XState v5)
 *
 * Hierarchical state machine managing finance page lock/unlock flow.
 * States:
 *   - checking: Initial state, transitions via guard to locked/unlocked
 *   - locked: Sub-states for connection test flow (idle -> testing -> succeeded/failed)
 *   - unlocked: Sub-states for data loading (loading -> loaded/error)
 *
 * Invoked actors (not ad-hoc useEffect):
 *   - testConnection: Calls POST /api/adapters for connection test
 *   - fetchFinanceData: Calls GET /api/dashboard/finance for financial data
 *
 * Uses setup() API for full TypeScript typing of context, events, guards.
 */

import { setup, fromPromise } from 'xstate';
import type { CapabilityEnvelope } from '../lib/adminClient';

// ── Context & Events ─────────────────────────────────────────────────────────

export interface FinancePageContext {
  envelope: CapabilityEnvelope | null;
  credentials: Record<string, string> | null;
  transactions: Transaction[];
  summary: FinanceSummary | null;
  error: string | null;
}

export interface Transaction {
  id: string;
  timestamp: string;
  amount: number;
  currency: string;
  category: string;
  merchant: string;
  account_id: string;
  pending: boolean;
  platform: string;
}

export interface FinanceSummary {
  total_expenses_period: number;
  total_income_period: number;
  net_cashflow: number;
  recent_count: number;
  platforms: string[];
  page: number;
  total_pages: number;
  available_categories: string[];
}

export type FinancePageEvent =
  | { type: 'SUBMIT_CREDENTIALS'; credentials: Record<string, string> }
  | { type: 'DISMISS' }
  | { type: 'RETRY' }
  | { type: 'REFRESH' };

// ── Guards ───────────────────────────────────────────────────────────────────

function financeAdapterLocked(context: FinancePageContext): boolean {
  const financeAdapter = context.envelope?.adapters.find(
    (a) => a.category === 'finance'
  );
  return financeAdapter?.locked ?? true;
}

// ── Invoked Actors ───────────────────────────────────────────────────────────

async function testConnection({
  input,
}: {
  input: { credentials: Record<string, string> };
}): Promise<{ success: boolean; error?: string }> {
  try {
    const response = await fetch('/api/adapters', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        category: 'finance',
        action: 'test_connection',
        credentials: input.credentials,
      }),
    });

    const data = await response.json();

    if (!response.ok) {
      return { success: false, error: data.error || 'Connection test failed' };
    }

    return { success: true };
  } catch (err) {
    return {
      success: false,
      error: err instanceof Error ? err.message : 'Network error',
    };
  }
}

async function fetchFinanceData(): Promise<{
  transactions: Transaction[];
  summary: FinanceSummary;
}> {
  try {
    const response = await fetch('/api/dashboard/finance', {
      cache: 'no-store',
    });

    if (!response.ok) {
      throw new Error(`Finance API returned ${response.status}`);
    }

    const data = await response.json();

    return {
      transactions: data.transactions || [],
      summary: {
        total_expenses_period: data.total_expenses_period || 0,
        total_income_period: data.total_income_period || 0,
        net_cashflow: data.net_cashflow || 0,
        recent_count: data.recent_count || 0,
        platforms: data.platforms || [],
        page: data.page || 1,
        total_pages: data.total_pages || 1,
        available_categories: data.available_categories || [],
      },
    };
  } catch (err) {
    throw new Error(
      err instanceof Error ? err.message : 'Failed to fetch finance data'
    );
  }
}

// ── XState v5 Machine Setup ──────────────────────────────────────────────────

export const financePageMachine = setup({
  types: {
    context: {} as FinancePageContext,
    events: {} as FinancePageEvent,
    input: {} as { envelope: CapabilityEnvelope | null },
  },

  actors: {
    testConnection: fromPromise(testConnection),
    fetchFinanceData: fromPromise(fetchFinanceData),
  },

  guards: {
    financeAdapterLocked: ({ context }) => financeAdapterLocked(context),
  },

  actions: {
    storeCredentials: ({ context, event }) => {
      if (event.type === 'SUBMIT_CREDENTIALS') {
        context.credentials = event.credentials;
      }
    },

    clearError: ({ context }) => {
      context.error = null;
    },

    storeError: ({ context, event }) => {
      if ('error' in event && typeof event.error === 'string') {
        context.error = event.error;
      }
    },

    storeFinanceData: ({ context, event }) => {
      if (event.type === 'xstate.done.actor.fetchFinanceData' && event.output) {
        context.transactions = event.output.transactions;
        context.summary = event.output.summary;
        context.error = null;
      }
    },
  },
}).createMachine({
  id: 'financePage',
  initial: 'checking',
  context: ({ input }) => ({
    envelope: input.envelope,
    credentials: null,
    transactions: [],
    summary: null,
    error: null,
  }),

  states: {
    // Check initial lock status
    checking: {
      always: [
        {
          guard: 'financeAdapterLocked',
          target: 'locked',
        },
        {
          target: 'unlocked',
        },
      ],
    },

    // Finance adapter locked — need credentials
    locked: {
      initial: 'idle',
      states: {
        idle: {
          on: {
            SUBMIT_CREDENTIALS: {
              target: 'testing',
              actions: ['storeCredentials', 'clearError'],
            },
          },
        },

        testing: {
          invoke: {
            src: 'testConnection',
            input: ({ context }) => ({ credentials: context.credentials || {} }),
            onDone: [
              {
                guard: ({ event }) => event.output.success,
                target: 'succeeded',
              },
              {
                target: 'failed',
                actions: ({ context, event }) => {
                  context.error = event.output.error || 'Connection test failed';
                },
              },
            ],
            onError: {
              target: 'failed',
              actions: ({ context, event }) => {
                context.error =
                  (event.error as Error)?.message || 'Connection test error';
              },
            },
          },
        },

        failed: {
          on: {
            SUBMIT_CREDENTIALS: {
              target: 'testing',
              actions: ['storeCredentials', 'clearError'],
            },
            DISMISS: 'idle',
          },
        },

        succeeded: {
          type: 'final',
        },
      },

      onDone: {
        target: 'unlocked',
      },
    },

    // Finance adapter unlocked — fetch data
    unlocked: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchFinanceData',
            onDone: {
              target: 'loaded',
              actions: ({ context, event }) => {
                context.transactions = event.output.transactions;
                context.summary = event.output.summary;
                context.error = null;
              },
            },
            onError: {
              target: 'error',
              actions: ({ context, event }) => {
                context.error =
                  (event.error as Error)?.message || 'Failed to load finance data';
              },
            },
          },
        },

        loaded: {
          on: {
            REFRESH: 'loading',
          },
        },

        error: {
          on: {
            RETRY: 'loading',
          },
        },
      },
    },
  },
});
