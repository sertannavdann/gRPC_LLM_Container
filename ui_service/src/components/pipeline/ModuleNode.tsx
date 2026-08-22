/**
 * ModuleNode — React Flow custom node for NEXUS dynamic modules.
 *
 * Renders five visually distinct lifecycle states across the build -> validate ->
 * approve/reject flow (D-13), plus the original running/disabled/failed admin
 * toggle chrome as a fallback for already-loaded modules with no lifecycle data.
 *
 * Lifecycle states (see resolveLifecycle() for the derivation contract):
 *   - building        live scaffold/implement/tests/repair stage progression (D-13)
 *   - validating      amber fallback when an in-flight module has no live stage yet
 *   - pendingApproval static amber border + pulsing orange "Needs Review" badge (D-01/D-04)
 *   - approved        green border, one-shot spring entrance
 *   - rejected        red border, entrance shake (Phase 6 no-silent-fallback)
 *   - legacy          original stateStyles map (running/disabled/failed admin toggle)
 */
'use client';

import React, { memo } from 'react';
import { Handle, Position, type NodeProps } from '@xyflow/react';
import { motion, type MotionProps } from 'framer-motion';
import { Puzzle, Power, PowerOff, Eye } from 'lucide-react';

export interface ModuleNodeData {
  label: string;
  category: string;
  state: 'running' | 'disabled' | 'failed';
  moduleId: string;
  onToggle?: (id: string, enable: boolean) => void;
  pendingApproval?: boolean;
  status?: string;
  buildStage?: string;
  [key: string]: unknown;
}

// Legacy lifecycle fallback map — running/disabled/failed remain the base styling
// when none of the richer lifecycle states below apply (kept, not rewritten).
const stateStyles: Record<string, { border: string; badge: string; badgeText: string }> = {
  running: { border: 'border-blue-500/60 bg-blue-500/10', badge: 'bg-blue-500/20', badgeText: 'text-blue-300' },
  disabled: { border: 'border-zinc-600/40 bg-zinc-800/40', badge: 'bg-zinc-600/20', badgeText: 'text-zinc-400' },
  failed: { border: 'border-red-500/60 bg-red-500/10', badge: 'bg-red-500/20', badgeText: 'text-red-300' },
};

// Reused VERBATIM from PipelineStageFlow.tsx's STAGE_COLORS (UI-SPEC §4 forbids
// redefining these). Keyed 'test' (singular) — the SSE `build_stage` contract
// (plan 08-03) uses 'tests' (plural, from AttemptRecord.stage). Mapped explicitly
// via stageColorKey() below; do not rename either side.
const STAGE_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  scaffold: { border: '#3b82f6', bg: 'bg-blue-500/10', text: 'text-blue-400' },
  implement: { border: '#8b5cf6', bg: 'bg-purple-500/10', text: 'text-purple-400' },
  test: { border: '#f59e0b', bg: 'bg-amber-500/10', text: 'text-amber-400' },
  repair: { border: '#ef4444', bg: 'bg-red-500/10', text: 'text-red-400' },
};

const BUILD_STAGE_NAMES = ['scaffold', 'implement', 'tests', 'repair'];

/** Explicit tests(plural, SSE build_stage) -> test(singular, STAGE_COLORS) mapping. */
function stageColorKey(stage: string): string {
  return stage === 'tests' ? 'test' : stage;
}

export type ModuleLifecycle =
  | 'pendingApproval'
  | 'approved'
  | 'rejected'
  | 'building'
  | 'validating'
  | 'legacy';

/**
 * Pure, testable derivation of a module node's lifecycle state from its data props.
 * Precedence order (08-08-PLAN.md Task 1) so no branch is unreachable:
 *   1. pendingApproval === true                          -> 'pendingApproval'
 *   2. status is approved|installed                      -> 'approved'
 *   3. status is failed|rejected (or state === 'failed')  -> 'rejected'
 *   4. buildStage in {scaffold,implement,tests,repair}    -> 'building'
 *   5. status in {pending,validating}                     -> 'validating' (amber fallback)
 *   6. otherwise                                          -> 'legacy' (stateStyles[d.state])
 */
export function resolveLifecycle(d: ModuleNodeData): ModuleLifecycle {
  if (d.pendingApproval === true) return 'pendingApproval';
  if (d.status === 'approved' || d.status === 'installed') return 'approved';
  if (d.status === 'failed' || d.status === 'rejected' || d.state === 'failed') return 'rejected';
  if (d.buildStage && BUILD_STAGE_NAMES.includes(d.buildStage)) return 'building';
  if (d.status === 'pending' || d.status === 'validating') return 'validating';
  return 'legacy';
}

function NodeShell({
  children,
  className,
  style,
  motionProps,
}: {
  children: React.ReactNode;
  className: string;
  style?: React.CSSProperties;
  motionProps?: MotionProps;
}) {
  return (
    <div className="relative">
      <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
      <motion.div className={className} style={style} {...motionProps}>
        {children}
      </motion.div>
      <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
    </div>
  );
}

function ModuleNodeComponent({ data }: NodeProps) {
  const d = data as unknown as ModuleNodeData;
  const lifecycle = resolveLifecycle(d);

  // ---- legacy: original running/disabled/failed rendering, unchanged ----
  if (lifecycle === 'legacy') {
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

  // ---- building: border cycles through the live build stage's color (D-13) ----
  if (lifecycle === 'building') {
    const stage = d.buildStage as string;
    const colors = STAGE_COLORS[stageColorKey(stage)] ?? STAGE_COLORS.scaffold;
    return (
      <NodeShell
        className={`rounded-lg border-2 px-4 py-3 min-w-[170px] shadow-md ${colors.bg}`}
        style={{ borderColor: colors.border }}
        motionProps={{
          animate: { borderColor: [colors.border, '#8b5cf6', colors.border] },
          transition: { repeat: Infinity, duration: 2, ease: 'easeInOut' },
        }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0 bg-blue-400 animate-pulse" />
          <Puzzle className="w-4 h-4 text-blue-300" />
          <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${colors.bg} ${colors.text}`}>
            {d.category}
          </span>
          <span className={`text-[10px] ${colors.text}`}>{stage}</span>
        </div>
      </NodeShell>
    );
  }

  // ---- validating: amber fallback for in-flight modules with no live stage detail ----
  if (lifecycle === 'validating') {
    const colors = STAGE_COLORS.test;
    return (
      <NodeShell
        className={`rounded-lg border-2 px-4 py-3 min-w-[170px] shadow-md ${colors.bg}`}
        style={{ borderColor: colors.border }}
        motionProps={{
          animate: { borderColor: [colors.border, '#8b5cf6', colors.border] },
          transition: { repeat: Infinity, duration: 2, ease: 'easeInOut' },
        }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <span className="w-2 h-2 rounded-full flex-shrink-0 bg-blue-400 animate-pulse" />
          <Puzzle className="w-4 h-4 text-blue-300" />
          <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
        </div>
        <div className="flex items-center justify-between">
          <span className={`text-[10px] px-1.5 py-0.5 rounded ${colors.bg} ${colors.text}`}>
            {d.category}
          </span>
          <span className={`text-[10px] ${colors.text}`}>validating</span>
        </div>
      </NodeShell>
    );
  }

  // ---- pendingApproval: static amber border + pulsing orange "Needs Review" badge ----
  // Deliberately non-pulsing border (vs 'validating's pulsing border) — the badge
  // pulse IS the notification per D-04. UI-SPEC Flag 6: do not collapse this
  // distinction with 'validating'.
  if (lifecycle === 'pendingApproval') {
    return (
      <div className="relative">
        <Handle type="target" position={Position.Left} className="!bg-zinc-500" />
        <motion.div
          className="absolute -top-2 -right-2 z-10 w-[18px] h-[18px] rounded-full bg-orange-500 flex items-center justify-center shadow-md"
          animate={{ scale: [1, 1.08, 1] }}
          transition={{ duration: 1.8, repeat: Infinity, ease: 'easeInOut' }}
        >
          <Eye className="w-3 h-3 text-white" />
        </motion.div>
        <div className="rounded-lg border-2 border-amber-500/60 bg-amber-500/10 px-4 py-3 min-w-[170px] shadow-md">
          <div className="flex items-center gap-2 mb-1">
            <Puzzle className="w-4 h-4 text-blue-300" />
            <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
          </div>
          <div className="text-[10px] text-amber-400 mb-1">· Needs Review</div>
          <div className="flex items-center justify-between">
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/20 text-amber-300">
              {d.category}
            </span>
          </div>
        </div>
        <Handle type="source" position={Position.Right} className="!bg-zinc-500" />
      </div>
    );
  }

  // ---- approved: green border, one-shot spring entrance ----
  if (lifecycle === 'approved') {
    return (
      <NodeShell
        className="rounded-lg border-2 px-4 py-3 min-w-[170px] shadow-md bg-green-500/10"
        style={{ borderColor: '#22c55e' }}
        motionProps={{
          initial: { scale: 1 },
          animate: { scale: [1, 1.05, 1] },
          transition: { duration: 0.3, type: 'spring' },
        }}
      >
        <div className="flex items-center gap-2 mb-1.5">
          <Puzzle className="w-4 h-4 text-green-300" />
          <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
        </div>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-500/20 text-green-300">
          {d.category}
        </span>
      </NodeShell>
    );
  }

  // ---- rejected: red border with entrance shake (Phase 6 no-silent-fallback: the
  // node must render explicitly for at least one SSE cycle, not vanish silently) ----
  return (
    <NodeShell
      className="rounded-lg border-2 px-4 py-3 min-w-[170px] shadow-md bg-red-500/10"
      style={{ borderColor: '#ef4444' }}
      motionProps={{
        initial: { x: 0 },
        animate: { x: [0, -10, 10, -10, 10, 0] },
        transition: { duration: 0.5 },
      }}
    >
      <div className="flex items-center gap-2 mb-1.5">
        <Puzzle className="w-4 h-4 text-red-300" />
        <span className="text-sm font-medium text-zinc-100 truncate">{d.label}</span>
      </div>
      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-500/20 text-red-300">
        {d.category}
      </span>
    </NodeShell>
  );
}

export const ModuleNode = memo(ModuleNodeComponent);
