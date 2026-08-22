/**
 * BlueprintCard — Progressive blueprint summary for a module (D-05).
 *
 * Collapsed state: a "technical-drawing aesthetic" card reusing StageNode's
 * dashed-border look, with a 4-row structural summary (Adapter / Schema /
 * Outputs / Credentials). This collapsed view is also the ONLY view used by
 * the chat ApprovalActionCard (plan 08-11), hence the `expandable` prop.
 *
 * Expanded state: a read-only, fixed-layout React Flow mini-graph rendering
 * the static 4-node chain Adapter -> Schema -> Outputs -> Credentials.
 */
'use client';

import React, { memo, useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  ReactFlow,
  Handle,
  Position,
  type Node,
  type Edge,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { ChevronDown } from 'lucide-react';
import type { ModuleBlueprint } from '@/lib/adminClient';

interface BlueprintCardProps {
  blueprint: ModuleBlueprint;
  moduleName: string;
  expandable?: boolean;
}

// ── Mini-graph node (local to this file — not registered in the page's
//    global nodeTypes) ───────────────────────────────────────────────────────

interface MiniNodeData {
  label: string;
  detail: string;
  [key: string]: unknown;
}

function MiniStageNodeComponent({ data }: NodeProps) {
  const d = data as unknown as MiniNodeData;
  return (
    <div className="rounded-lg border-2 border-dashed border-zinc-600/40 bg-zinc-800/30 px-2.5 py-1.5 min-w-[100px] shadow-sm">
      <Handle type="target" position={Position.Left} className="!bg-zinc-600" />
      <div className="text-[11px] font-semibold text-zinc-200 truncate">{d.label}</div>
      <div className="text-[10px] text-zinc-500 truncate">{d.detail}</div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-600" />
    </div>
  );
}

const miniNodeTypes = { miniStage: memo(MiniStageNodeComponent) };

function buildMiniGraph(blueprint: ModuleBlueprint, moduleName: string): { nodes: Node[]; edges: Edge[] } {
  const steps: { id: string; label: string; detail: string }[] = [
    { id: 'adapter', label: 'Adapter', detail: blueprint.adapter_name || moduleName },
    { id: 'schema', label: 'Schema', detail: `${blueprint.schema_field_count} fields` },
    {
      id: 'outputs',
      label: 'Outputs',
      detail:
        blueprint.output_types.length > 0
          ? blueprint.output_types.join(', ')
          : `${blueprint.output_types.length} types`,
    },
    {
      id: 'credentials',
      label: 'Credentials',
      detail: `${blueprint.credential_names.length} required`,
    },
  ];

  const nodes: Node[] = steps.map((step, i) => ({
    id: step.id,
    type: 'miniStage',
    position: { x: i * 160, y: 0 },
    data: { label: step.label, detail: step.detail } satisfies MiniNodeData,
    draggable: false,
    selectable: false,
  }));

  const edges: Edge[] = steps.slice(1).map((step, i) => ({
    id: `e-${steps[i].id}-${step.id}`,
    source: steps[i].id,
    target: step.id,
    animated: false,
    style: { stroke: '#52525b' }, // zinc-600
  }));

  return { nodes, edges };
}

// ── Summary row ──────────────────────────────────────────────────────────────

function SummaryRow({ label, count }: { label: string; count: number }) {
  return (
    <div className="flex items-center justify-between text-sm">
      <span className="flex items-center gap-1.5 text-zinc-400">
        <span className="w-1.5 h-1.5 rounded-full bg-zinc-600" />
        {label}
      </span>
      <span className="text-zinc-200">{count}</span>
    </div>
  );
}

// ── BlueprintCard ────────────────────────────────────────────────────────────

export function BlueprintCard({ blueprint, moduleName, expandable = true }: BlueprintCardProps) {
  const [expanded, setExpanded] = useState(false);

  const outputsLabel =
    blueprint.output_types.length > 0
      ? `Outputs (${blueprint.output_types.join(', ')})`
      : 'Outputs';

  const isEmpty =
    blueprint.schema_field_count === 0 &&
    blueprint.output_types.length === 0 &&
    blueprint.credential_names.length === 0;

  const { nodes, edges } = buildMiniGraph(blueprint, moduleName);

  return (
    <div className="border border-dashed border-zinc-600/50 bg-zinc-950/40 rounded-lg p-3">
      <div className="text-xs font-mono text-zinc-300 mb-2 truncate">
        {blueprint.adapter_name || moduleName}
      </div>

      <div className="space-y-1.5">
        <SummaryRow label="Adapter" count={blueprint.adapter_name ? 1 : 0} />
        <SummaryRow label="Schema" count={blueprint.schema_field_count} />
        <SummaryRow label={outputsLabel} count={blueprint.output_types.length} />
        <SummaryRow label="Credentials" count={blueprint.credential_names.length} />
      </div>

      {isEmpty && (
        <p className="text-[11px] text-zinc-500 italic mt-2">
          This adapter could not be statically summarized.
        </p>
      )}

      {expandable && (
        <button
          onClick={() => setExpanded((v) => !v)}
          className="flex items-center gap-1 mt-2 text-orange-400 text-xs hover:text-orange-300 transition-colors"
        >
          <ChevronDown
            className={`w-3.5 h-3.5 transition-transform ${expanded ? 'rotate-180' : ''}`}
          />
          {expanded ? 'Collapse blueprint' : 'Expand blueprint'}
        </button>
      )}

      <AnimatePresence>
        {expandable && expanded && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 256, opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2, ease: 'easeOut' }}
            className="overflow-hidden mt-2"
          >
            <div className="h-64 rounded-md border border-zinc-800 bg-zinc-950/60">
              <ReactFlow
                nodes={nodes}
                edges={edges}
                nodeTypes={miniNodeTypes}
                nodesDraggable={false}
                elementsSelectable={false}
                panOnDrag={false}
                zoomOnScroll={false}
                proOptions={{ hideAttribution: true }}
                fitView
              />
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
