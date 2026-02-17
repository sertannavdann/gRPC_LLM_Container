/**
 * PipelineStageFlow Component
 *
 * React Flow v12 pipeline stage visualization with custom PipelineStageNode.
 * Renders build pipeline stages (scaffold -> implement -> test -> repair) as
 * a horizontal flow with animated borders for in-progress stages.
 *
 * Stage color mapping:
 *   scaffold: blue, implement: purple, test: amber, repair: red
 *
 * Academic anchor: Agentic Builder-Tester Pattern §5 (agent monitoring dashboards)
 */

'use client';

import React, { useMemo, useCallback } from 'react';
import {
  ReactFlow,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { motion } from 'framer-motion';
import type { AgentRun } from '../../machines/monitoringPage';

// ── Stage Color Map ─────────────────────────────────────────────────────────

const STAGE_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  scaffold: { border: '#3b82f6', bg: 'bg-blue-500/10', text: 'text-blue-400' },
  implement: { border: '#8b5cf6', bg: 'bg-purple-500/10', text: 'text-purple-400' },
  test: { border: '#f59e0b', bg: 'bg-amber-500/10', text: 'text-amber-400' },
  repair: { border: '#ef4444', bg: 'bg-red-500/10', text: 'text-red-400' },
};

const STATUS_DOT: Record<string, string> = {
  running: 'bg-blue-400 animate-pulse',
  completed: 'bg-green-400',
  failed: 'bg-red-400',
};

// ── Custom Pipeline Stage Node ──────────────────────────────────────────────

interface PipelineStageData {
  label: string;
  stage: string;
  status: string;
  attempts: number;
  module: string;
  [key: string]: unknown;
}

export function PipelineStageNode({ data }: NodeProps<Node<PipelineStageData>>) {
  const stage = data.stage || 'scaffold';
  const colors = STAGE_COLORS[stage] || STAGE_COLORS.scaffold;
  const isInProgress = data.status === 'running';

  return (
    <div className="relative">
      <Handle type="target" position={Position.Left} className="!bg-border" />

      <motion.div
        className={`rounded-lg px-3 py-2.5 min-w-[130px] border-2 ${colors.bg}`}
        style={{ borderColor: colors.border }}
        animate={
          isInProgress
            ? { borderColor: ['#3b82f6', '#8b5cf6', '#3b82f6'] }
            : undefined
        }
        transition={
          isInProgress
            ? { repeat: Infinity, duration: 2, ease: 'easeInOut' }
            : undefined
        }
      >
        {/* Stage label + status dot */}
        <div className="flex items-center gap-1.5 mb-1">
          <span className={`w-2 h-2 rounded-full flex-shrink-0 ${STATUS_DOT[data.status] || STATUS_DOT.completed}`} />
          <span className={`text-xs font-semibold uppercase ${colors.text}`}>
            {data.label}
          </span>
        </div>

        {/* Module name */}
        <div className="text-[10px] text-muted-foreground truncate max-w-[120px]">
          {data.module}
        </div>

        {/* Attempt counter */}
        <div className="text-[10px] text-muted-foreground mt-0.5">
          Attempt {data.attempts}/10
        </div>
      </motion.div>

      <Handle type="source" position={Position.Right} className="!bg-border" />
    </div>
  );
}

// ── Pipeline Flow Builder ───────────────────────────────────────────────────

const STAGE_ORDER = ['scaffold', 'implement', 'test', 'repair'];

function agentRunToFlow(run: AgentRun): { nodes: Node<PipelineStageData>[]; edges: Edge[] } {
  const nodes: Node<PipelineStageData>[] = [];
  const edges: Edge[] = [];
  const currentStageIdx = STAGE_ORDER.indexOf(run.stage);

  STAGE_ORDER.forEach((stage, idx) => {
    const nodeId = `${run.buildId}-${stage}`;
    let status: string;

    if (idx < currentStageIdx) {
      status = 'completed';
    } else if (idx === currentStageIdx) {
      status = run.status;
    } else {
      status = 'completed'; // Future stages not yet reached
    }

    // Only show stages up to current
    if (idx > currentStageIdx) return;

    nodes.push({
      id: nodeId,
      type: 'pipelineStageNode',
      position: { x: idx * 170, y: 0 },
      data: {
        label: stage,
        stage,
        status,
        attempts: idx === currentStageIdx ? run.attempts : 1,
        module: run.module,
      },
    });

    if (idx > 0) {
      const prevId = `${run.buildId}-${STAGE_ORDER[idx - 1]}`;
      edges.push({
        id: `${prevId}->${nodeId}`,
        source: prevId,
        target: nodeId,
        animated: status === 'running',
        style: { stroke: STAGE_COLORS[stage]?.border || '#6b7280' },
      });
    }
  });

  return { nodes, edges };
}

// ── PipelineStageFlow Component ─────────────────────────────────────────────

interface PipelineStageFlowProps {
  agentRuns: AgentRun[];
  maxRuns?: number;
}

const pipelineNodeTypes = { pipelineStageNode: PipelineStageNode };

export function PipelineStageFlow({ agentRuns, maxRuns = 3 }: PipelineStageFlowProps) {
  const { allNodes, allEdges } = useMemo(() => {
    const allNodes: Node<PipelineStageData>[] = [];
    const allEdges: Edge[] = [];

    const recentRuns = agentRuns.slice(0, maxRuns);

    recentRuns.forEach((run, rowIdx) => {
      const { nodes, edges } = agentRunToFlow(run);

      // Offset each run row vertically
      const yOffset = rowIdx * 90;
      nodes.forEach((n) => {
        n.position.y += yOffset;
        n.position.x += 10;
      });

      allNodes.push(...nodes);
      allEdges.push(...edges);
    });

    return { allNodes, allEdges };
  }, [agentRuns, maxRuns]);

  const onInit = useCallback(() => {}, []);

  if (agentRuns.length === 0) {
    return (
      <div className="flex items-center justify-center h-[200px] text-muted-foreground text-sm">
        No recent agent runs
      </div>
    );
  }

  return (
    <div className="w-full h-[280px] rounded-lg border border-border bg-card/50 overflow-hidden">
      <ReactFlow
        nodes={allNodes}
        edges={allEdges}
        nodeTypes={pipelineNodeTypes}
        onInit={onInit}
        fitView
        fitViewOptions={{ padding: 0.3 }}
        proOptions={{ hideAttribution: true }}
        className="bg-background"
        minZoom={0.5}
        maxZoom={1.5}
        nodesDraggable={false}
        nodesConnectable={false}
        elementsSelectable={false}
      >
      </ReactFlow>
    </div>
  );
}
