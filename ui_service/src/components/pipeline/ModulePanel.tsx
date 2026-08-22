/**
 * ModulePanel — Generic auto-generated output surface for installed modules
 * (D-07, UI-SPEC Component Contract §6).
 *
 * Renders any module's canonical `AdapterRunResult` envelope — key/value data
 * points, chart artifacts, and explicit empty/error states — without the
 * module shipping any UI code of its own. Fetches on demand via a "Run
 * module" button, never automatically on mount, because running a module
 * triggers a real outbound third-party API call (T-08-50).
 */
'use client';

import React from 'react';
import { Loader2, Play, FileText } from 'lucide-react';
import {
  BarChart,
  Bar,
  CartesianGrid,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { adminApi, type AdapterRunResult, type RunArtifact, type RunDataPoint } from '@/lib/adminClient';
import { DegradedBanner, EmptyState } from '@/components/ui/error-states';

interface ModulePanelProps {
  moduleId: string; // "category/platform"
}

const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
];

/**
 * Flattens a data point's `data` object one level into label/value rows,
 * reusing NodeDetailPanel's Status-row pattern verbatim.
 */
function DataPointRows({ point }: { point: RunDataPoint }) {
  const entries = Object.entries(point.data ?? {});
  return (
    <div className="space-y-2">
      <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
        {point.schema_ref}
      </h4>
      <div className="space-y-1.5">
        {entries.length === 0 ? (
          <p className="text-xs text-zinc-500">No fields returned.</p>
        ) : (
          entries.map(([key, value]) => (
            <div key={key} className="flex items-center justify-between text-sm">
              <span className="text-muted-foreground">{key}</span>
              <span className="text-foreground truncate max-w-[60%] text-right">
                {typeof value === 'object' && value !== null
                  ? JSON.stringify(value)
                  : String(value)}
              </span>
            </div>
          ))
        )}
      </div>
    </div>
  );
}

/**
 * Renders a chart artifact using ONLY its declared `type`/`mime_type`
 * metadata — never sniffed from the data shape (UI-SPEC Flag 4). Artifact
 * `bytes` for chart types are expected to be a JSON-encoded array of
 * {name, value}-shaped rows; anything else falls back to the generic
 * artifact row rather than guessing.
 */
function ChartArtifact({ artifact }: { artifact: RunArtifact }) {
  let rows: Array<Record<string, unknown>> | null = null;
  if (artifact.mime_type === 'application/json') {
    try {
      const parsed = JSON.parse(artifact.bytes);
      if (Array.isArray(parsed)) rows = parsed;
    } catch {
      rows = null;
    }
  }

  if (!rows || rows.length === 0) {
    return <ArtifactRow artifact={artifact} />;
  }

  const keys = Object.keys(rows[0]).filter((k) => k !== 'name');
  const valueKey = keys[0] ?? 'value';

  // Chart shape declared by the artifact's own `name` convention keeps this
  // generic — default to a bar chart, the safest default for arbitrary
  // categorical data points without inferring structure.
  return (
    <div className="space-y-1.5">
      <h4 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
        {artifact.name}
      </h4>
      <ResponsiveContainer width="100%" height={220} initialDimension={{ width: 400, height: 220 }}>
        <BarChart data={rows} margin={{ top: 10, right: 10, left: 0, bottom: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
          <XAxis dataKey="name" stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} />
          <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} tickLine={false} />
          <Tooltip
            contentStyle={{
              backgroundColor: 'hsl(var(--card))',
              borderColor: 'hsl(var(--border))',
              borderRadius: '8px',
            }}
            labelStyle={{ color: 'hsl(var(--foreground))' }}
          />
          <Bar dataKey={valueKey} fill={CHART_COLORS[0]} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

/** Non-chart artifacts render as a labelled row with name and size — never raw bytes. */
function ArtifactRow({ artifact }: { artifact: RunArtifact }) {
  return (
    <div className="flex items-center justify-between text-sm px-2 py-1.5 rounded bg-zinc-800/60">
      <span className="flex items-center gap-1.5 text-foreground">
        <FileText className="w-3.5 h-3.5 text-muted-foreground" />
        {artifact.name}
      </span>
      <span className="text-muted-foreground text-xs">
        {artifact.type}
        {typeof artifact.size === 'number' ? ` · ${artifact.size}B` : ''}
      </span>
    </div>
  );
}

export function ModulePanel({ moduleId }: ModulePanelProps) {
  const [category, platform] = moduleId.split('/');
  const [running, setRunning] = React.useState(false);
  const [result, setResult] = React.useState<AdapterRunResult | null>(null);
  const [fetchError, setFetchError] = React.useState<string | null>(null);

  const handleRun = React.useCallback(async () => {
    if (!category || !platform) return;
    setRunning(true);
    setFetchError(null);
    try {
      const runResult = await adminApi.runModule(category, platform);
      setResult(runResult);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : 'Failed to run module');
    } finally {
      setRunning(false);
    }
  }, [category, platform]);

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide">
          Module Output
        </h3>
        <button
          onClick={handleRun}
          disabled={running}
          className="flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium bg-primary text-primary-foreground hover:bg-primary/90 disabled:opacity-50 transition-colors"
        >
          {running ? (
            <>
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Running...
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5" />
              Run module
            </>
          )}
        </button>
      </div>

      {fetchError && (
        <DegradedBanner feature="Module run" reasons={[fetchError]} onRetry={handleRun} />
      )}

      {!fetchError && result && result.errors.length > 0 && (
        <DegradedBanner
          feature={result.run.module_id}
          reasons={result.errors.map((e) => (e.detail ? `${e.message} — ${e.detail}` : e.message))}
          onRetry={handleRun}
        />
      )}

      {!fetchError && result && result.errors.length === 0 && (
        <>
          {result.data_points.length === 0 && result.artifacts.length === 0 ? (
            <EmptyState
              title="No data yet"
              description="This module hasn't returned any data. Run it from the pipeline or ask the assistant to use it."
            />
          ) : (
            <div className="space-y-4">
              {result.data_points.map((point, i) => (
                <DataPointRows key={`${point.schema_ref}-${i}`} point={point} />
              ))}
              {result.artifacts.map((artifact, i) =>
                artifact.type === 'chart' ? (
                  <ChartArtifact key={`${artifact.name}-${i}`} artifact={artifact} />
                ) : (
                  <ArtifactRow key={`${artifact.name}-${i}`} artifact={artifact} />
                )
              )}
            </div>
          )}
        </>
      )}

      {!fetchError && !result && (
        <p className="text-xs text-zinc-500">Run this module to see its output here.</p>
      )}
    </div>
  );
}
