/**
 * Monitoring Page
 *
 * Full monitoring dashboard with:
 * - XState monitoringPageMachine driving parallel state regions (health, latency, tabs)
 * - React Flow v12 interactive service topology with custom ServiceNode
 * - Recharts BarChart for P99/P95/P50 latency with 500ms target ReferenceLine
 * - React Flow pipeline stage visualization for agent build runs
 * - Agent runs table with sortable columns
 * - Grafana embed tabs (overview, modules, alerts)
 *
 * Dynamic imports for React Flow and Recharts (SSR disabled for client-only rendering).
 *
 * Academic anchors:
 * - EDMO §6.1: P99 benchmarks, event-to-action latency target
 * - Agentic Builder-Tester §5: Agent monitoring dashboards
 */
'use client';

import React from 'react';
import dynamic from 'next/dynamic';
import { useMachine } from '@xstate/react';
import { monitoringPageMachine, type AgentRun } from '../../machines/monitoringPage';
import { useNexusApp } from '../../hooks/useNexusApp';
import {
  Activity,
  RefreshCw,
  ExternalLink,
  Signal,
  Clock,
  Workflow,
  AlertTriangle,
  CheckCircle2,
  XCircle,
  Loader2,
} from 'lucide-react';

// ── Dynamic Imports (SSR disabled) ──────────────────────────────────────────

const ServiceTopology = dynamic(
  () => import('../../components/monitoring/ServiceTopology').then((m) => m.ServiceTopology),
  { ssr: false, loading: () => <SkeletonPanel height="420px" /> },
);

const LatencyChart = dynamic(
  () => import('../../components/monitoring/LatencyChart').then((m) => m.LatencyChart),
  { ssr: false, loading: () => <SkeletonPanel height="300px" /> },
);

const PipelineStageFlow = dynamic(
  () => import('../../components/monitoring/PipelineStageFlow').then((m) => m.PipelineStageFlow),
  { ssr: false, loading: () => <SkeletonPanel height="280px" /> },
);

// ── Skeleton Components ─────────────────────────────────────────────────────

function SkeletonPanel({ height }: { height: string }) {
  return (
    <div
      className="animate-pulse bg-muted/40 rounded-lg border border-border"
      style={{ height }}
    />
  );
}

function SkeletonCard() {
  return (
    <div className="animate-pulse bg-muted/40 rounded-lg border border-border h-24" />
  );
}

// ── Grafana Configuration ───────────────────────────────────────────────────

const GRAFANA_URL =
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:3001`
    : 'http://localhost:3001';

const GRAFANA_DASHBOARDS = {
  overview: '/d/grpc-llm-overview/grpc-llm-overview',
  modules: '/d/service-health/service-health',
  alerts: '/d/tool-execution/tool-execution',
};

// ── Status Badge ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: string }) {
  const config: Record<string, { icon: React.ReactNode; cls: string }> = {
    healthy: { icon: <CheckCircle2 className="w-3 h-3" />, cls: 'bg-green-500/20 text-green-400' },
    degraded: { icon: <AlertTriangle className="w-3 h-3" />, cls: 'bg-amber-500/20 text-amber-400' },
    unavailable: { icon: <XCircle className="w-3 h-3" />, cls: 'bg-red-500/20 text-red-400' },
    unknown: { icon: <Signal className="w-3 h-3" />, cls: 'bg-gray-500/20 text-gray-400' },
  };

  const c = config[status] || config.unknown;

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium ${c.cls}`}>
      {c.icon}
      {status.toUpperCase()}
    </span>
  );
}

// ── Agent Runs Table ────────────────────────────────────────────────────────

function AgentRunsTable({ runs }: { runs: AgentRun[] }) {
  if (runs.length === 0) {
    return (
      <div className="flex items-center justify-center h-32 text-muted-foreground text-sm">
        No recent agent runs
      </div>
    );
  }

  const statusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />;
      case 'running':
        return <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />;
      case 'failed':
        return <XCircle className="w-3.5 h-3.5 text-red-400" />;
      default:
        return null;
    }
  };

  return (
    <div className="overflow-auto max-h-[260px]">
      <table className="w-full text-sm">
        <thead className="sticky top-0 bg-card">
          <tr className="border-b border-border">
            <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Build ID</th>
            <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Module</th>
            <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Stage</th>
            <th className="text-left py-2 px-3 text-muted-foreground font-medium text-xs">Status</th>
            <th className="text-right py-2 px-3 text-muted-foreground font-medium text-xs">Duration</th>
            <th className="text-right py-2 px-3 text-muted-foreground font-medium text-xs">Attempts</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.buildId} className="border-b border-border/50 hover:bg-muted/30 transition-colors">
              <td className="py-2 px-3 font-mono text-xs">{run.buildId}</td>
              <td className="py-2 px-3 text-xs">{run.module}</td>
              <td className="py-2 px-3">
                <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-muted text-muted-foreground uppercase">
                  {run.stage}
                </span>
              </td>
              <td className="py-2 px-3">
                <span className="flex items-center gap-1">
                  {statusIcon(run.status)}
                  <span className="text-xs">{run.status}</span>
                </span>
              </td>
              <td className="py-2 px-3 text-right text-xs text-muted-foreground">
                {(run.duration / 1000).toFixed(1)}s
              </td>
              <td className="py-2 px-3 text-right text-xs">
                <span className={run.attempts >= 5 ? 'text-red-400' : 'text-muted-foreground'}>
                  {run.attempts}/10
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ── Main Monitoring Page ────────────────────────────────────────────────────

export default function MonitoringPage() {
  const [state, send] = useMachine(monitoringPageMachine);
  const { envelope, isLive } = useNexusApp();

  // Parallel region states
  const isHealthLoading = state.matches({ health: 'loading' });
  const isHealthError = state.matches({ health: 'error' });
  const isLatencyLoading = state.matches({ latency: 'loading' });
  const isLatencyError = state.matches({ latency: 'error' });

  // Active tab
  const activeTab = state.matches({ activeTab: 'overview' })
    ? 'overview'
    : state.matches({ activeTab: 'modules' })
    ? 'modules'
    : 'alerts';

  // Data from context
  const { features, latencyData, agentRuns, healthError, latencyError } = state.context;

  // Merge envelope features with machine features
  const displayFeatures = features.length > 0 ? features : envelope?.features || [];

  return (
    <div className="flex flex-col h-full overflow-auto">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-border bg-card/60 flex-shrink-0">
        <div className="flex items-center gap-3">
          <Activity className="w-5 h-5 text-orange-400" />
          <h1 className="text-lg font-semibold">Monitoring</h1>
          <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
            <span className={`w-2 h-2 rounded-full ${isLive ? 'bg-green-500 animate-pulse' : 'bg-gray-500'}`} />
            {isLive ? 'Live' : 'Polling'}
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => {
              send({ type: 'REFRESH_HEALTH' });
              send({ type: 'REFRESH_LATENCY' });
            }}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs rounded-md bg-muted hover:bg-muted/80 text-foreground transition-colors"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${isHealthLoading || isLatencyLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
          <a
            href={GRAFANA_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="flex items-center gap-1 px-3 py-1.5 text-xs rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          >
            Grafana <ExternalLink className="w-3 h-3" />
          </a>
        </div>
      </div>

      {/* Content */}
      <div className="flex-1 p-6 space-y-6">
        {/* Section 1: Feature Health Cards */}
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Signal className="w-4 h-4" />
            Service Health
          </h2>

          {isHealthError && (
            <div className="mb-3 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400 flex items-center gap-2">
              <AlertTriangle className="w-4 h-4 flex-shrink-0" />
              {healthError || 'Failed to load health data'}
              <button
                onClick={() => send({ type: 'REFRESH_HEALTH' })}
                className="ml-auto text-xs underline"
              >
                Retry
              </button>
            </div>
          )}

          {isHealthLoading && displayFeatures.length === 0 ? (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {[1, 2, 3, 4].map((i) => (
                <SkeletonCard key={i} />
              ))}
            </div>
          ) : (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {displayFeatures.map((feature) => (
                <div
                  key={feature.feature}
                  className="bg-card border border-border rounded-lg p-3"
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="text-sm font-medium capitalize">
                      {feature.feature}
                    </span>
                    <StatusBadge status={feature.status} />
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {feature.dependencies?.join(', ')}
                  </div>
                  {feature.degraded_reasons && feature.degraded_reasons.length > 0 && (
                    <div className="mt-1.5 text-[10px] text-amber-400/80">
                      {feature.degraded_reasons.map((r, i) => (
                        <div key={i}>{r}</div>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          )}
        </section>

        {/* Section 2: Service Topology (React Flow) */}
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Workflow className="w-4 h-4" />
            Service Topology
          </h2>
          <ServiceTopology features={displayFeatures} latencyData={latencyData} />
        </section>

        {/* Section 3: Latency + Agent Runs (side by side) */}
        <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {/* Latency Chart */}
          <section>
            <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
              <Clock className="w-4 h-4" />
              P99 Latency
            </h2>

            {isLatencyError && (
              <div className="mb-3 px-3 py-2 bg-red-500/10 border border-red-500/30 rounded-lg text-sm text-red-400 flex items-center gap-2">
                <AlertTriangle className="w-4 h-4 flex-shrink-0" />
                {latencyError || 'Failed to load latency data'}
                <button
                  onClick={() => send({ type: 'REFRESH_LATENCY' })}
                  className="ml-auto text-xs underline"
                >
                  Retry
                </button>
              </div>
            )}

            <div className="bg-card border border-border rounded-lg p-3">
              <LatencyChart data={latencyData} />
            </div>
          </section>

          {/* Agent Runs Table */}
          <section>
            <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
              <Workflow className="w-4 h-4" />
              Agent Runs
            </h2>
            <div className="bg-card border border-border rounded-lg">
              <AgentRunsTable runs={agentRuns} />
            </div>
          </section>
        </div>

        {/* Section 4: Pipeline Stage Flow (React Flow) */}
        <section>
          <h2 className="text-sm font-medium text-muted-foreground mb-3 flex items-center gap-2">
            <Workflow className="w-4 h-4" />
            Build Pipeline Stages
          </h2>
          <PipelineStageFlow agentRuns={agentRuns} />
        </section>

        {/* Section 5: Grafana Tab Group */}
        <section>
          <div className="flex items-center gap-3 mb-3">
            <h2 className="text-sm font-medium text-muted-foreground">Grafana Dashboards</h2>
            <div className="flex items-center gap-1 bg-muted rounded-lg p-0.5">
              {(['overview', 'modules', 'alerts'] as const).map((tab) => (
                <button
                  key={tab}
                  onClick={() =>
                    send({
                      type: tab === 'overview'
                        ? 'TAB_OVERVIEW'
                        : tab === 'modules'
                        ? 'TAB_MODULES'
                        : 'TAB_ALERTS',
                    })
                  }
                  className={`px-2.5 py-1 text-xs rounded-md transition-colors capitalize ${
                    activeTab === tab
                      ? 'bg-primary text-primary-foreground font-medium'
                      : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>

          <div className="border border-border rounded-lg overflow-hidden">
            <iframe
              src={`${GRAFANA_URL}${GRAFANA_DASHBOARDS[activeTab]}?orgId=1&kiosk`}
              className="w-full h-[400px] border-0"
              title={`Grafana ${activeTab} Dashboard`}
            />
          </div>
        </section>
      </div>
    </div>
  );
}
