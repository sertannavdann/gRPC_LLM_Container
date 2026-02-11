/**
 * ServiceNode — React Flow custom node for infrastructure services.
 * Shows service name, state (running/error/idle), and latency.
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Server, AlertTriangle, Pause } from 'lucide-react';

export interface ServiceNodeData {
  label: string;
  state: 'running' | 'error' | 'idle';
  latency_ms: number;
  [key: string]: unknown;
}

const stateColors: Record<string, string> = {
  running: 'border-green-500/60 bg-green-500/10',
  error: 'border-red-500/60 bg-red-500/10',
  idle: 'border-zinc-500/40 bg-zinc-500/10',
};

const stateIcons: Record<string, React.ReactNode> = {
  running: <span className="w-2 h-2 rounded-full bg-green-400 animate-pulse" />,
  error: <AlertTriangle className="w-3.5 h-3.5 text-red-400" />,
  idle: <Pause className="w-3.5 h-3.5 text-zinc-400" />,
};

function ServiceNodeComponent({ data }: NodeProps) {
  const d = data as unknown as ServiceNodeData;
  return (
    <div className={`rounded-lg border px-4 py-3 min-w-[160px] shadow-md ${stateColors[d.state] ?? stateColors.idle}`}>
      <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
      <div className="flex items-center gap-2 mb-1">
        <Server className="w-4 h-4 text-zinc-300" />
        <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
      </div>
      <div className="flex items-center justify-between text-xs text-zinc-400">
        <span className="flex items-center gap-1">
          {stateIcons[d.state] ?? stateIcons.idle}
          {d.state}
        </span>
        {d.latency_ms > 0 && <span>{d.latency_ms}ms</span>}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
    </div>
  );
}

export const ServiceNode = memo(ServiceNodeComponent);
