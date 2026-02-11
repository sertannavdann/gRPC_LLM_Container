/**
 * ModuleNode — React Flow custom node for NEXUS dynamic modules.
 * Shows module name, category, state, and enable/disable toggle.
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Puzzle, Power, PowerOff } from 'lucide-react';

export interface ModuleNodeData {
  label: string;
  category: string;
  state: 'running' | 'disabled' | 'failed';
  moduleId: string;
  onToggle?: (id: string, enable: boolean) => void;
  [key: string]: unknown;
}

const stateStyles: Record<string, { border: string; badge: string; badgeText: string }> = {
  running: { border: 'border-blue-500/60 bg-blue-500/10', badge: 'bg-blue-500/20', badgeText: 'text-blue-300' },
  disabled: { border: 'border-zinc-600/40 bg-zinc-800/40', badge: 'bg-zinc-600/20', badgeText: 'text-zinc-400' },
  failed: { border: 'border-red-500/60 bg-red-500/10', badge: 'bg-red-500/20', badgeText: 'text-red-300' },
};

function ModuleNodeComponent({ data }: NodeProps) {
  const d = data as unknown as ModuleNodeData;
  const style = stateStyles[d.state] ?? stateStyles.disabled;

  return (
    <div className={`rounded-lg border px-4 py-3 min-w-[170px] shadow-md ${style.border}`}>
      <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
      <div className="flex items-center gap-2 mb-1.5">
        <Puzzle className="w-4 h-4 text-blue-300" />
        <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
      </div>
      <div className="flex items-center justify-between">
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${style.badge} ${style.badgeText}`}>
          {d.category}
        </span>
        {d.onToggle && (
          <button
            onClick={(e) => { e.stopPropagation(); d.onToggle?.(d.moduleId, d.state !== 'running'); }}
            className="p-1 rounded hover:bg-zinc-700/50 transition-colors"
            title={d.state === 'running' ? 'Disable module' : 'Enable module'}
          >
            {d.state === 'running'
              ? <Power className="w-3.5 h-3.5 text-green-400" />
              : <PowerOff className="w-3.5 h-3.5 text-zinc-500" />}
          </button>
        )}
      </div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
    </div>
  );
}

export const ModuleNode = memo(ModuleNodeComponent);
