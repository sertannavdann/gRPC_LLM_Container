/**
 * StageNode — React Flow custom node for pipeline processing stages.
 * Represents a logical stage in the decision pipeline (intent, routing, tools, synthesis).
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Workflow } from 'lucide-react';

export interface StageNodeData {
  label: string;
  description?: string;
  active?: boolean;
  [key: string]: unknown;
}

function StageNodeComponent({ data }: NodeProps) {
  const d = data as unknown as StageNodeData;
  return (
    <div
      className={`rounded-xl border-2 border-dashed px-5 py-3 min-w-[150px] shadow-sm transition-colors ${
        d.active
          ? 'border-orange-400/60 bg-orange-500/10'
          : 'border-zinc-600/40 bg-zinc-800/30'
      }`}
    >
      <Handle type="target" position={Position.Left} className="!bg-orange-400" />
      <div className="flex items-center gap-2">
        <Workflow className={`w-4 h-4 ${d.active ? 'text-orange-400' : 'text-zinc-500'}`} />
        <span className="text-sm font-semibold text-zinc-100">{d.label}</span>
      </div>
      {d.description && (
        <p className="text-[11px] text-zinc-400 mt-1">{d.description}</p>
      )}
      <Handle type="source" position={Position.Right} className="!bg-orange-400" />
      <Handle type="source" position={Position.Bottom} id="bottom" className="!bg-amber-400" />
    </div>
  );
}

export const StageNode = memo(StageNodeComponent);
