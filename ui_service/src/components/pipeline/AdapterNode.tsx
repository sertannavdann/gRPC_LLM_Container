/**
 * AdapterNode — React Flow custom node for data adapters.
 * Shows adapter name, category, state, and auth status.
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { Database, Lock } from 'lucide-react';

export interface AdapterNodeData {
  label: string;
  adapterId: string;
  category: string;
  platform: string;
  state: 'running' | 'error' | 'disabled';
  requiresAuth: boolean;
  hasCredentials: boolean;
  onClick?: (adapterId: string) => void;
  [key: string]: unknown;
}

const stateStyles: Record<string, { border: string; dot: string }> = {
  running: { border: 'border-green-500/60 bg-green-500/10', dot: 'bg-green-400' },
  error: { border: 'border-red-500/60 bg-red-500/10', dot: 'bg-red-400' },
  disabled: { border: 'border-zinc-600/40 bg-zinc-800/40', dot: 'bg-zinc-500' },
};

const categoryColors: Record<string, string> = {
  weather: 'bg-sky-500/20 text-sky-300',
  finance: 'bg-emerald-500/20 text-emerald-300',
  calendar: 'bg-violet-500/20 text-violet-300',
  health: 'bg-pink-500/20 text-pink-300',
  navigation: 'bg-blue-500/20 text-blue-300',
  gaming: 'bg-orange-500/20 text-orange-300',
};

function AdapterNodeComponent({ data }: NodeProps) {
  const d = data as unknown as AdapterNodeData;
  const style = stateStyles[d.state] ?? stateStyles.disabled;
  const locked = d.requiresAuth && !d.hasCredentials;
  const catColor = categoryColors[d.category] ?? 'bg-zinc-600/20 text-zinc-400';

  return (
    <div
      className={`rounded-lg border px-3.5 py-2.5 min-w-[130px] shadow-md cursor-pointer hover:brightness-110 transition-all ${
        locked ? 'border-yellow-500/60 bg-yellow-500/10' : style.border
      }`}
      onClick={(e) => {
        e.stopPropagation();
        d.onClick?.(d.adapterId);
      }}
    >
      <Handle type="target" position={Position.Top} className="!bg-zinc-400" />
      <div className="flex items-center gap-2 mb-1">
        <Database className="w-3.5 h-3.5 text-zinc-300" />
        <span className="text-xs font-medium text-zinc-100 truncate max-w-[100px]">{d.label}</span>
        {locked && <Lock className="w-3 h-3 text-yellow-400 flex-shrink-0" />}
      </div>
      <div className="flex items-center justify-between">
        <span className={`text-[10px] px-1.5 py-0.5 rounded ${catColor}`}>
          {d.category}
        </span>
        <span className="flex items-center gap-1 text-[10px] text-zinc-400">
          <span className={`w-1.5 h-1.5 rounded-full ${style.dot}`} />
          {locked ? 'locked' : d.state}
        </span>
      </div>
    </div>
  );
}

export const AdapterNode = memo(AdapterNodeComponent);
