/**
 * LatencyChart Component
 *
 * Recharts BarChart displaying P50/P95/P99 latency per service.
 * Color coding: P50 green, P95 amber, P99 red.
 * 500ms ReferenceLine marks the P99 target threshold.
 *
 * Uses ResponsiveContainer with initialDimension for SSR safety.
 * Academic anchor: EDMO §6.1 (1.2s event-to-action latency target, P99 benchmarks)
 */

'use client';

import React from 'react';
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ReferenceLine,
  ResponsiveContainer,
  Legend,
} from 'recharts';
import type { ServiceLatency } from '../../machines/monitoringPage';

// ── LatencyChart Component ──────────────────────────────────────────────────

interface LatencyChartProps {
  data: ServiceLatency[];
}

export function LatencyChart({ data }: LatencyChartProps) {
  if (!data || data.length === 0) {
    return (
      <div className="flex items-center justify-center h-[300px] text-muted-foreground">
        No latency data available
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={300} initialDimension={{ width: 600, height: 300 }}>
      <BarChart data={data} margin={{ top: 10, right: 20, left: 0, bottom: 10 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
        <XAxis
          dataKey="service"
          stroke="hsl(var(--muted-foreground))"
          fontSize={11}
          tickLine={false}
          angle={-15}
          textAnchor="end"
          height={50}
        />
        <YAxis
          stroke="hsl(var(--muted-foreground))"
          fontSize={12}
          tickLine={false}
          label={{
            value: 'ms',
            position: 'insideLeft',
            style: { fill: 'hsl(var(--muted-foreground))', fontSize: 12 },
          }}
        />
        <Tooltip
          contentStyle={{
            backgroundColor: 'hsl(var(--card))',
            borderColor: 'hsl(var(--border))',
            borderRadius: '8px',
            color: 'hsl(var(--foreground))',
          }}
          labelStyle={{ color: 'hsl(var(--foreground))' }}
          formatter={(value: number, name: string) => [
            `${value}ms`,
            name.toUpperCase(),
          ]}
        />
        <Legend
          verticalAlign="top"
          height={30}
          iconType="rect"
          formatter={(value) => (
            <span style={{ color: 'hsl(var(--foreground))', fontSize: '12px' }}>
              {value.toUpperCase()}
            </span>
          )}
        />

        {/* P99 target reference line at 500ms */}
        <ReferenceLine
          y={500}
          stroke="#ef4444"
          strokeDasharray="6 3"
          label={{
            value: 'P99 Target',
            position: 'right',
            fill: '#ef4444',
            fontSize: 11,
          }}
        />

        {/* Grouped bars */}
        <Bar dataKey="p50" fill="#22c55e" name="p50" radius={[2, 2, 0, 0]} />
        <Bar dataKey="p95" fill="#f59e0b" name="p95" radius={[2, 2, 0, 0]} />
        <Bar dataKey="p99" fill="#ef4444" name="p99" radius={[2, 2, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}
