/**
 * ServiceTopology Component
 *
 * React Flow v12 interactive service topology graph with custom ServiceNode components.
 * Transforms CapabilityEnvelope features[] into nodes and edges.
 *
 * Custom ServiceNode embeds shadcn/ui Card + Badge with:
 * - Status dot (green/amber/red) mapped from FeatureHealth
 * - Framer Motion pulse animation on DEGRADED status
 * - P99 Badge showing latency with destructive variant > 500ms
 *
 * Academic anchor: EDMO §6.1 (P99 benchmarks, event-to-action latency target)
 */

'use client';

import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { motion } from 'framer-motion';
import type { FeatureHealth } from '../../lib/adminClient';
import type { ServiceLatency } from '../../machines/monitoringPage';

// ── Status Color Map ────────────────────────────────────────────────────────

const STATUS_COLORS: Record<string, string> = {
  healthy: '#22c55e',   // green-500
  degraded: '#f59e0b',  // amber-500
  unavailable: '#ef4444', // red-500
  unknown: '#6b7280',   // gray-500
};

const STATUS_BG: Record<string, string> = {
  healthy: 'bg-green-500/20 text-green-400',
  degraded: 'bg-amber-500/20 text-amber-400',
  unavailable: 'bg-red-500/20 text-red-400',
  unknown: 'bg-gray-500/20 text-gray-400',
};

// ── Custom Service Node ─────────────────────────────────────────────────────

interface ServiceNodeData {
  label: string;
  status: string;
  p99?: number;
  degradedReasons?: string[];
  [key: string]: unknown;
}

export function ServiceNode({ data }: NodeProps<Node<ServiceNodeData>>) {
  const status = data.status || 'unknown';
  const statusColor = STATUS_COLORS[status] || STATUS_COLORS.unknown;
  const isDegraded = status === 'degraded';
  const p99 = data.p99;

  return (
    <div className="relative">
      <Handle type="target" position={Position.Top} className="!bg-border" />

      <motion.div
        className="bg-card border border-border rounded-lg shadow-md px-4 py-3 min-w-[160px]"
        animate={
          isDegraded
            ? { scale: [1, 1.02, 1] }
            : undefined
        }
        transition={
          isDegraded
            ? { repeat: Infinity, duration: 2, ease: 'easeInOut' }
            : undefined
        }
      >
        {/* Header with status dot */}
        <div className="flex items-center gap-2 mb-1.5">
          <span
            className="w-2.5 h-2.5 rounded-full flex-shrink-0"
            style={{ backgroundColor: statusColor }}
          />
          <span className="text-sm font-medium text-foreground truncate">
            {data.label}
          </span>
        </div>

        {/* Status badge */}
        <div className="flex items-center gap-1.5 flex-wrap">
          <span className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${STATUS_BG[status] || STATUS_BG.unknown}`}>
            {status.toUpperCase()}
          </span>

          {/* P99 badge */}
          {p99 !== undefined && (
            <span
              className={`inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium ${
                p99 > 500
                  ? 'bg-red-500/20 text-red-400'
                  : 'bg-muted text-muted-foreground'
              }`}
            >
              P99: {p99}ms
            </span>
          )}
        </div>

        {/* Degraded reasons tooltip */}
        {isDegraded && data.degradedReasons && data.degradedReasons.length > 0 && (
          <div className="mt-1.5 text-[10px] text-amber-400/80 leading-tight">
            {data.degradedReasons.map((reason, i) => (
              <div key={i}>{reason}</div>
            ))}
          </div>
        )}
      </motion.div>

      <Handle type="source" position={Position.Bottom} className="!bg-border" />
    </div>
  );
}

// ── Topology Builder ────────────────────────────────────────────────────────

/**
 * Transform CapabilityEnvelope features[] + latency data into React Flow nodes and edges.
 *
 * Layout:
 *   Row 1 (top):    Orchestrator
 *   Row 2 (middle): LLM Gateway, Sandbox, ChromaDB
 *   Row 3 (bottom): UI Service, Dashboard, Bridge
 */
export function envelopeToTopology(
  features: FeatureHealth[],
  latencyData: ServiceLatency[],
): { nodes: Node<ServiceNodeData>[]; edges: Edge[] } {
  // Map feature names to display config
  const serviceMap: Record<string, { label: string; row: number; col: number }> = {
    providers: { label: 'Orchestrator', row: 0, col: 1 },
    modules: { label: 'LLM Gateway', row: 1, col: 0 },
    sandbox: { label: 'Sandbox', row: 1, col: 1 },
    adapters: { label: 'ChromaDB', row: 1, col: 2 },
    billing: { label: 'UI Service', row: 2, col: 0 },
    pipeline: { label: 'Dashboard', row: 2, col: 1 },
  };

  // Extra services always present
  const allServices: { id: string; label: string; row: number; col: number; status: string; reasons: string[] }[] = [];

  // Add feature-based services
  for (const feature of features) {
    const config = serviceMap[feature.feature];
    if (config) {
      allServices.push({
        id: feature.feature,
        label: config.label,
        row: config.row,
        col: config.col,
        status: feature.status,
        reasons: feature.degraded_reasons || [],
      });
    }
  }

  // Add Bridge service (always present)
  allServices.push({
    id: 'bridge',
    label: 'Bridge',
    row: 2,
    col: 2,
    status: 'healthy',
    reasons: [],
  });

  // If no features provided, show default topology
  if (allServices.length <= 1) {
    const defaults = [
      { id: 'orchestrator', label: 'Orchestrator', row: 0, col: 1, status: 'unknown', reasons: [] },
      { id: 'llm-gateway', label: 'LLM Gateway', row: 1, col: 0, status: 'unknown', reasons: [] },
      { id: 'sandbox', label: 'Sandbox', row: 1, col: 1, status: 'unknown', reasons: [] },
      { id: 'chromadb', label: 'ChromaDB', row: 1, col: 2, status: 'unknown', reasons: [] },
      { id: 'ui-service', label: 'UI Service', row: 2, col: 0, status: 'unknown', reasons: [] },
      { id: 'dashboard', label: 'Dashboard', row: 2, col: 1, status: 'unknown', reasons: [] },
      { id: 'bridge', label: 'Bridge', row: 2, col: 2, status: 'unknown', reasons: [] },
    ];
    allServices.splice(0, allServices.length, ...defaults);
  }

  // Build latency lookup
  const latencyLookup: Record<string, number> = {};
  for (const l of latencyData) {
    latencyLookup[l.service] = l.p99;
  }

  // Create nodes with positions
  const COL_GAP = 220;
  const ROW_GAP = 140;
  const X_OFFSET = 50;
  const Y_OFFSET = 40;

  const nodes: Node<ServiceNodeData>[] = allServices.map((svc) => ({
    id: svc.id,
    type: 'serviceNode',
    position: {
      x: X_OFFSET + svc.col * COL_GAP,
      y: Y_OFFSET + svc.row * ROW_GAP,
    },
    data: {
      label: svc.label,
      status: svc.status,
      p99: latencyLookup[svc.label],
      degradedReasons: svc.reasons,
    },
  }));

  // Create edges (hub-and-spoke from orchestrator)
  const orchestratorId = allServices.find((s) => s.label === 'Orchestrator')?.id;
  const edges: Edge[] = [];

  if (orchestratorId) {
    const middleRow = allServices.filter((s) => s.row === 1);
    const bottomRow = allServices.filter((s) => s.row === 2);

    for (const svc of middleRow) {
      edges.push({
        id: `${orchestratorId}-${svc.id}`,
        source: orchestratorId,
        target: svc.id,
        animated: svc.status === 'healthy' || svc.status === 'degraded',
        style: { stroke: STATUS_COLORS[svc.status] || '#6b7280' },
      });
    }

    for (const svc of bottomRow) {
      // Connect bottom row to middle row (closest by column)
      const closest = middleRow.reduce((prev, curr) =>
        Math.abs(curr.col - svc.col) < Math.abs(prev.col - svc.col) ? curr : prev,
        middleRow[0],
      );
      if (closest) {
        edges.push({
          id: `${closest.id}-${svc.id}`,
          source: closest.id,
          target: svc.id,
          animated: svc.status === 'healthy',
          style: { stroke: '#4b5563' },
        });
      }
    }
  }

  return { nodes, edges };
}

// ── ServiceTopology Component ───────────────────────────────────────────────

interface ServiceTopologyProps {
  features: FeatureHealth[];
  latencyData: ServiceLatency[];
}

const nodeTypes = { serviceNode: ServiceNode };

export function ServiceTopology({ features, latencyData }: ServiceTopologyProps) {
  const { nodes, edges } = useMemo(
    () => envelopeToTopology(features, latencyData),
    [features, latencyData],
  );

  const onInit = useCallback(() => {
    // React Flow initialized
  }, []);

  return (
    <div className="w-full h-[420px] rounded-lg border border-border bg-card/50 overflow-hidden">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        onInit={onInit}
        fitView
        fitViewOptions={{ padding: 0.2 }}
        proOptions={{ hideAttribution: true }}
        className="bg-background"
        minZoom={0.5}
        maxZoom={1.5}
      >
        <Background gap={20} size={1} color="hsl(var(--border))" />
        <Controls className="!bg-card !border-border !shadow-md" />
        <MiniMap
          nodeColor={(node) => {
            const data = node.data as ServiceNodeData;
            return STATUS_COLORS[data.status] || STATUS_COLORS.unknown;
          }}
          className="!bg-card !border-border"
          maskColor="rgba(0,0,0,0.3)"
        />
      </ReactFlow>
    </div>
  );
}
