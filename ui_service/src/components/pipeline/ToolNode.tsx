/**
 * ToolNode — React Flow custom node for pipeline tools.
 * Shows tool name, connected adapter count, and stage association.
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Wrench } from 'lucide-react';

export interface ToolNodeData {
  label: string;
  connectedAdapters: string[];
  stage: string;
  onClick?: (toolName: string) => void;
  [key: string]: unknown;
}

function ToolNodeComponent({ data }: NodeProps) {
  const d = data as unknown as ToolNodeData;
  const adapterCount = d.connectedAdapters?.length ?? 0;

  return (
    <div
      className="rounded-lg border border-amber-500/60 bg-amber-500/10 px-4 py-2.5 min-w-[140px] shadow-md cursor-pointer hover:bg-amber-500/20 transition-colors"
      onClick={(e) => {
        e.stopPropagation();
        d.onClick?.(d.label);
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-amber-400" />
      <div className="flex items-center gap-2">
        <Wrench className="w-3.5 h-3.5 text-amber-400" />
        <span className="text-xs font-medium text-zinc-100 truncate">{d.label}</span>
      </div>
      {adapterCount > 0 && (
        <div className="mt-1.5 flex items-center gap-1">
          <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">
            {adapterCount} adapter{adapterCount !== 1 ? 's' : ''}
          </span>
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-amber-400" />
    </div>
  );
}

export const ToolNode = memo(ToolNodeComponent);
