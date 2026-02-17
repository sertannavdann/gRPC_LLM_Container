/**
 * Monitoring Page Statechart (XState v5)
 *
 * Parallel state machine managing monitoring page with three independent regions:
 * 1. health: Feature health polling (auto-refresh 30s, error retry 5s)
 * 2. latency: Latency snapshot polling (auto-refresh 60s, error retry 10s)
 * 3. activeTab: Tab selection (overview | modules | alerts)
 *
 * Each region uses invoked actors (fromPromise) for async data fetching.
 * Academic anchor: Harel Statecharts with parallel (orthogonal) regions.
 */

import { setup, fromPromise } from 'xstate';
import { adminApi, type FeatureHealth } from '../lib/adminClient';

// ── Types ───────────────────────────────────────────────────────────────────

export interface ServiceLatency {
  service: string;
  p50: number;
  p95: number;
  p99: number;
}

export interface AgentRun {
  buildId: string;
  module: string;
  stage: 'scaffold' | 'implement' | 'test' | 'repair';
  status: 'running' | 'completed' | 'failed';
  duration: number;
  attempts: number;
}

export interface MonitoringPageContext {
  features: FeatureHealth[];
  latencyData: ServiceLatency[];
  agentRuns: AgentRun[];
  healthError: string | null;
  latencyError: string | null;
}

export type MonitoringPageEvent =
  | { type: 'TAB_OVERVIEW' }
  | { type: 'TAB_MODULES' }
  | { type: 'TAB_ALERTS' }
  | { type: 'REFRESH_HEALTH' }
  | { type: 'REFRESH_LATENCY' };

// ── Mock Data for Development ───────────────────────────────────────────────

function generateMockLatencyData(): ServiceLatency[] {
  return [
    { service: 'Orchestrator', p50: 45, p95: 120, p99: 280 },
    { service: 'LLM Gateway', p50: 180, p95: 420, p99: 650 },
    { service: 'Dashboard', p50: 25, p95: 65, p99: 110 },
    { service: 'Sandbox', p50: 90, p95: 250, p99: 480 },
    { service: 'ChromaDB', p50: 35, p95: 80, p99: 150 },
    { service: 'UI Service', p50: 15, p95: 40, p99: 75 },
    { service: 'Bridge', p50: 20, p95: 55, p99: 95 },
  ];
}

function generateMockAgentRuns(): AgentRun[] {
  return [
    { buildId: 'b-001', module: 'weather/openweather', stage: 'test', status: 'completed', duration: 12400, attempts: 1 },
    { buildId: 'b-002', module: 'finance/cibc', stage: 'repair', status: 'running', duration: 8200, attempts: 3 },
    { buildId: 'b-003', module: 'gaming/clashroyale', stage: 'implement', status: 'completed', duration: 15600, attempts: 1 },
    { buildId: 'b-004', module: 'calendar/google', stage: 'scaffold', status: 'completed', duration: 3100, attempts: 1 },
    { buildId: 'b-005', module: 'weather/openweather', stage: 'repair', status: 'failed', duration: 45000, attempts: 10 },
  ];
}

// ── XState v5 Machine Setup ─────────────────────────────────────────────────

export const monitoringPageMachine = setup({
  types: {
    context: {} as MonitoringPageContext,
    events: {} as MonitoringPageEvent,
  },

  actors: {
    fetchFeatureHealth: fromPromise(async () => {
      try {
        const features = await adminApi.getFeatureHealth();
        return features;
      } catch {
        // Return mock data on failure for development
        return [
          { feature: 'modules', status: 'healthy', degraded_reasons: [], dependencies: ['module_registry'] },
          { feature: 'providers', status: 'degraded', degraded_reasons: ['1 provider locked'], dependencies: ['routing_config'] },
          { feature: 'adapters', status: 'healthy', degraded_reasons: [], dependencies: ['credential_store'] },
          { feature: 'billing', status: 'healthy', degraded_reasons: [], dependencies: ['quota_manager'] },
        ] as FeatureHealth[];
      }
    }),

    fetchLatencySnapshot: fromPromise(async () => {
      try {
        const response = await fetch('/api/monitoring/latency');
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json() as { latency: ServiceLatency[]; agentRuns: AgentRun[] };
      } catch {
        // Return mock data for development
        return {
          latency: generateMockLatencyData(),
          agentRuns: generateMockAgentRuns(),
        };
      }
    }),
  },

  guards: {
    isHealthRetryable: ({ context }) => context.healthError !== null,
    isLatencyRetryable: ({ context }) => context.latencyError !== null,
  },
}).createMachine({
  id: 'monitoringPage',
  type: 'parallel',
  context: {
    features: [],
    latencyData: [],
    agentRuns: [],
    healthError: null,
    latencyError: null,
  },

  states: {
    // Region 1: Feature health polling
    health: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchFeatureHealth',
            onDone: {
              target: 'loaded',
              actions: ({ context, event }) => {
                context.features = event.output as FeatureHealth[];
                context.healthError = null;
              },
            },
            onError: {
              target: 'error',
              actions: ({ context, event }) => {
                context.healthError =
                  (event.error as Error)?.message || 'Failed to fetch health';
              },
            },
          },
        },

        loaded: {
          after: {
            30000: 'loading', // Auto-refresh every 30s
          },
          on: {
            REFRESH_HEALTH: 'loading',
          },
        },

        error: {
          after: {
            5000: {
              target: 'loading', // Auto-retry after 5s
            },
          },
          on: {
            REFRESH_HEALTH: 'loading',
          },
        },
      },
    },

    // Region 2: Latency snapshot polling
    latency: {
      initial: 'loading',
      states: {
        loading: {
          invoke: {
            src: 'fetchLatencySnapshot',
            onDone: {
              target: 'loaded',
              actions: ({ context, event }) => {
                const output = event.output as { latency: ServiceLatency[]; agentRuns: AgentRun[] };
                context.latencyData = output.latency;
                context.agentRuns = output.agentRuns;
                context.latencyError = null;
              },
            },
            onError: {
              target: 'error',
              actions: ({ context, event }) => {
                context.latencyError =
                  (event.error as Error)?.message || 'Failed to fetch latency';
              },
            },
          },
        },

        loaded: {
          after: {
            60000: 'loading', // Auto-refresh every 60s
          },
          on: {
            REFRESH_LATENCY: 'loading',
          },
        },

        error: {
          after: {
            10000: {
              target: 'loading', // Auto-retry after 10s
            },
          },
          on: {
            REFRESH_LATENCY: 'loading',
          },
        },
      },
    },

    // Region 3: Active tab selection
    activeTab: {
      initial: 'overview',
      states: {
        overview: {},
        modules: {},
        alerts: {},
      },
      on: {
        TAB_OVERVIEW: '.overview',
        TAB_MODULES: '.modules',
        TAB_ALERTS: '.alerts',
      },
    },
  },
});
