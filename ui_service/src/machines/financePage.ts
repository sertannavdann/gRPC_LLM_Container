/**
 * Finance Page Statechart (XState v5)
 *
 * Hierarchical state machine managing the finance page data flow.
 * States:
 *   - unlocked: Sub-states for data loading (loading -> loaded/error) and
 *     CSV upload (uploading -> loading, so the table refetches)
 *
 * The CIBC finance adapter needs no credentials, so there is no locked flow:
 * CSV exports are uploaded straight to the dashboard (POST /bank/upload).
 *
 * Invoked actors (not ad-hoc useEffect):
 *   - fetchFinanceData: Calls GET /api/dashboard/finance for financial data
 *   - uploadCsv: POSTs multipart FormData to /api/dashboard/finance/upload
 *
 * Uses setup() API for full TypeScript typing of context, events, guards.
 */

import { setup, fromPromise } from 'xstate';
import type { CapabilityEnvelope } from '../lib/adminClient';

// ── Context & Events ─────────────────────────────────────────────────────────

export interface FinancePageContext {
  envelope: CapabilityEnvelope | null;
  transactions: Transaction[];
  summary: FinanceSummary | null;
  error: string | null;
  pendingFile: File | null;
  uploadError: string | null;
  lastUpload: UploadResult | null;
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

export interface UploadResult {
  file: string;
  transactions: number;
}

export type FinancePageEvent =
  | { type: 'RETRY' }
  | { type: 'REFRESH' }
  | { type: 'UPLOAD_CSV'; file: File };

// ── Invoked Actors ───────────────────────────────────────────────────────────

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

async function uploadCsv({
  input,
}: {
  input: { file: File | null };
}): Promise<UploadResult> {
  if (!input.file) {
    throw new Error('No CSV file selected');
  }

  const form = new FormData();
  form.append('file', input.file, input.file.name);

  const response = await fetch('/api/dashboard/finance/upload', {
    method: 'POST',
    body: form,
  });

  const data = await response.json().catch(() => ({}));

  if (!response.ok || data.success === false) {
    const detail = data.detail ?? data.error;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : detail
          ? JSON.stringify(detail)
          : `Upload failed (HTTP ${response.status})`
    );
  }

  return {
    file: data.file || input.file.name,
    transactions: Number(data.transactions) || 0,
  };
}

// ── XState v5 Machine Setup ──────────────────────────────────────────────────

export const financePageMachine = setup({
  types: {
    context: {} as FinancePageContext,
    events: {} as FinancePageEvent,
    input: {} as { envelope: CapabilityEnvelope | null },
  },

  actors: {
    fetchFinanceData: fromPromise(fetchFinanceData),
    uploadCsv: fromPromise(uploadCsv),
  },

  actions: {
    storePendingFile: ({ context, event }) => {
      if (event.type === 'UPLOAD_CSV') {
        context.pendingFile = event.file;
        context.uploadError = null;
        context.lastUpload = null;
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
      // Called from onDone handler — event.output already typed via XState actor resolution
      const output = (event as any).output;
      if (output) {
        context.transactions = output.transactions;
        context.summary = output.summary;
        context.error = null;
      }
    },
  },
}).createMachine({
  id: 'financePage',
  initial: 'unlocked',
  context: ({ input }) => ({
    envelope: input.envelope,
    transactions: [],
    summary: null,
    error: null,
    pendingFile: null,
    uploadError: null,
    lastUpload: null,
  }),

  states: {
    // Finance adapter needs no credentials — fetch data
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
            UPLOAD_CSV: {
              target: 'uploading',
              actions: 'storePendingFile',
            },
          },
        },

        error: {
          on: {
            RETRY: 'loading',
            UPLOAD_CSV: {
              target: 'uploading',
              actions: 'storePendingFile',
            },
          },
        },

        // CSV upload in flight — success refetches via `loading`, failure
        // returns to `loaded` with the message in context.uploadError
        uploading: {
          invoke: {
            src: 'uploadCsv',
            input: ({ context }) => ({ file: context.pendingFile }),
            onDone: {
              target: 'loading',
              actions: ({ context, event }) => {
                context.lastUpload = event.output;
                context.pendingFile = null;
              },
            },
            onError: {
              target: 'loaded',
              actions: ({ context, event }) => {
                context.uploadError =
                  (event.error as Error)?.message || 'CSV upload failed';
                context.pendingFile = null;
              },
            },
          },
        },
      },
    },
  },
});
