/**
 * NEXUS Root Application Statechart (XState v5)
 *
 * Manages three parallel state regions:
 * 1. capability: Tool/module/provider/adapter capability polling
 * 2. dataSource: Live/mock/offline data source status (derived from adapter locks)
 * 3. auth: Authenticated/unauthenticated session state
 *
 * Uses XState v5 setup() API with full TypeScript typing.
 * ETag-based polling managed by invoked actors (replaces setInterval).
 *
 * Academic anchor: Harel Statecharts with parallel regions, guards, invoked actors
 */

import { setup, fromPromise } from 'xstate';
import { adminApi, CapabilityEnvelope } from '../lib/adminClient';
import { classifyError, NexusErrorType as ClassifiedError } from '../lib/errors';
import {
  CAPABILITY_RETRY_DELAY_MS,
  CONFIG_POLL_INTERVAL_MS,
} from '../lib/runtime-params';

// ── Context & Events ─────────────────────────────────────────────────────────

export interface NexusAppContext {
  envelope: CapabilityEnvelope | null;
  etag: string | null;
  configEtag: string | null;
  error: NexusErrorType | null;
  userPrefs: UserPreferences | null;
}

export interface UserPreferences {
  theme: 'light' | 'dark';
  autoRefresh: boolean;
}

export type NexusErrorType =
  | { type: 'TIMEOUT'; message: string }
  | { type: 'DEGRADED_PROVIDER'; message: string }
  | { type: 'NETWORK'; message: string }
  | { type: 'AUTH'; message: string }
  | { type: 'EMPTY'; message: string }
  | { type: 'UNKNOWN'; message: string };

export type NexusAppEvent =
  | { type: 'ENVELOPE_LOADED'; envelope: CapabilityEnvelope; etag: string }
  | { type: 'ENVELOPE_NOT_MODIFIED' }
  | { type: 'ENVELOPE_ERROR'; error: NexusErrorType }
  | { type: 'CONFIG_VERSION_CHANGED'; config_version: string; etag: string }
  | { type: 'CONFIG_VERSION_UNCHANGED' }
  | { type: 'CAPABILITY_REFRESH_REQUESTED' }
  | { type: 'AUTH_EXPIRED' }
  | { type: 'PREFS_LOADED'; prefs: UserPreferences };

// ── XState v5 Machine Setup ──────────────────────────────────────────────────

export const nexusAppMachine = setup({
  types: {
    context: {} as NexusAppContext,
    events: {} as NexusAppEvent,
  },

  actors: {
    pollCapabilities: fromPromise(async ({ input }: { input: { etag: string | null } }) => {
      const response = await adminApi.getCapabilities(input.etag || undefined);
      return response;
    }),

    pollConfigVersion: fromPromise(async ({ input }: { input: { etag: string | null } }) => {
      const response = await adminApi.getConfigVersion(input.etag || undefined);
      return response;
    }),
  },

  guards: {
    hasLiveAdapter: ({ context }) => {
      const unlockedAdapters = context.envelope?.adapters.filter((a) => !a.locked) || [];
      return unlockedAdapters.length > 0;
    },

    allAdaptersLocked: ({ context }) => {
      const adapters = context.envelope?.adapters || [];
      if (adapters.length === 0) return false;
      return adapters.every((a) => a.locked);
    },

    isFallbackEnvelope: ({ context }) => {
      return context.envelope?.snapshot_source === 'ui_admin_proxy';
    },

    isRetryableError: ({ context }) => {
      if (!context.error) return false;
      return context.error.type === 'TIMEOUT' || context.error.type === 'DEGRADED_PROVIDER';
    },

    configVersionChanged: ({ event }) => {
      return event.type === 'CONFIG_VERSION_CHANGED';
    },
  },

  actions: {
    storeEnvelope: ({ context, event }) => {
      if (event.type === 'ENVELOPE_LOADED') {
        context.envelope = event.envelope;
        context.etag = event.etag;
        context.error = null;
      }
    },

    storeConfigEtag: ({ context, event }) => {
      if (event.type === 'CONFIG_VERSION_CHANGED') {
        context.configEtag = event.etag;
      }
    },

    storeError: ({ context, event }) => {
      if (event.type === 'ENVELOPE_ERROR') {
        context.error = event.error;
      }
    },

    clearError: ({ context }) => {
      context.error = null;
    },

    storePrefs: ({ context, event }) => {
      if (event.type === 'PREFS_LOADED') {
        context.userPrefs = event.prefs;
      }
    },
  },
}).createMachine({
  id: 'nexusApp',
  type: 'parallel',
  context: {
    envelope: null,
    etag: null,
    configEtag: null,
    error: null,
    userPrefs: null,
  },

  states: {
    // Region 1: Capability polling
    capability: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'pollCapabilities',
            input: ({ context }) => ({ etag: context.etag }),
            onDone: {
              target: 'current',
              actions: [
                ({ context, event }) => {
                  if (!event.output.notModified && event.output.data) {
                    context.envelope = event.output.data;
                    context.etag = event.output.etag;

                    if (event.output.data.fallback_reason === 'admin_auth_required') {
                      context.error = {
                        type: 'AUTH',
                        message: 'Admin API key required for full dashboard capabilities.',
                      };
                    } else if (event.output.data.fallback_reason === 'upstream_unavailable') {
                      context.error = {
                        type: 'DEGRADED_PROVIDER',
                        message: 'Capability snapshot is in fallback mode while upstream is unavailable.',
                      };
                    } else if (event.output.data.adapters.length === 0) {
                      context.error = {
                        type: 'EMPTY',
                        message: 'No adapters are currently configured.',
                      };
                    } else {
                      context.error = null;
                    }
                  }
                },
              ],
            },
            onError: {
              target: 'error',
              actions: [
                ({ context, event }) => {
                  const errorMessage = (event.error as Error)?.message || 'Failed to fetch capabilities';
                  const kind = classifyError(event.error);
                  if (kind === ClassifiedError.NOT_AUTHORIZED) {
                    context.error = { type: 'AUTH', message: errorMessage };
                    return;
                  }
                  if (kind === ClassifiedError.DEGRADED_PROVIDER) {
                    context.error = { type: 'DEGRADED_PROVIDER', message: errorMessage };
                    return;
                  }
                  if (kind === ClassifiedError.TIMEOUT) {
                    context.error = { type: 'NETWORK', message: errorMessage };
                    return;
                  }
                  context.error = { type: 'UNKNOWN', message: errorMessage };
                },
              ],
            },
          },
        },

        current: {
          after: {
            [CONFIG_POLL_INTERVAL_MS]: 'polling',
          },
        },

        polling: {
          invoke: {
            src: 'pollConfigVersion',
            input: ({ context }) => ({ etag: context.configEtag }),
            onDone: [
              {
                guard: ({ event }) => {
                  return event.output.config_version !== '';
                },
                target: 'loading',
                actions: [
                  ({ context, event }) => {
                    context.configEtag = event.output.etag;
                  },
                ],
              },
              {
                // Config version unchanged, continue polling
                target: 'current',
              },
            ],
            onError: {
              target: 'error',
            },
          },
        },

        error: {
          on: {
            CAPABILITY_REFRESH_REQUESTED: 'loading',
          },
          after: {
            [CAPABILITY_RETRY_DELAY_MS]: [
              {
                guard: 'isRetryableError',
                target: 'loading', // Auto-retry retryable errors after 5s
              },
            ],
          },
        },
      },

      on: {
        CAPABILITY_REFRESH_REQUESTED: '.loading',
      },
    },

    // Region 2: Data source status (derived from adapter locks)
    dataSource: {
      initial: 'unknown',
      states: {
        unknown: {},
        live: {},
        mock: {},
        offline: {},
      },

      on: {
        ENVELOPE_LOADED: [
          {
            guard: 'isFallbackEnvelope',
            target: '.unknown',
          },
          {
            guard: 'hasLiveAdapter',
            target: '.live',
          },
          {
            guard: 'allAdaptersLocked',
            target: '.mock',
          },
          {
            target: '.offline',
          },
        ],
      },
    },

    // Region 3: Auth status
    auth: {
      initial: 'authenticated',
      states: {
        authenticated: {},
        unauthenticated: {},
      },

      on: {
        AUTH_EXPIRED: '.unauthenticated',
      },
    },
  },
});
