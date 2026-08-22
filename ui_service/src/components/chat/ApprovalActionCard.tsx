/**
 * ApprovalActionCard — chat-facing half of D-02.
 *
 * Extends the Phase 6 ActionCard structured-action pattern: same shell, same
 * pending/executing/completed/failed state machine, same AnimatePresence
 * transitions and failed-state shake keyframes. Adds a `Puzzle` header icon,
 * an inline collapsed BlueprintCard (never the expanded React Flow graph —
 * UI-SPEC Surface 5), an optional feedback textarea, and a two-click
 * terminal-rejection confirmation (D-09 / UI-SPEC Copywriting Contract).
 */

'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { motion, AnimatePresence } from 'framer-motion';
import { Check, X, Loader2, AlertTriangle, Puzzle } from 'lucide-react';
import { type ToolCall } from './ActionCard';
import { BlueprintCard } from '../pipeline/BlueprintCard';
import { DegradedBanner } from '../ui/error-states';
import { adminApi, type ModuleReview } from '@/lib/adminClient';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ApprovalActionCardProps {
  toolCall: ToolCall;
  moduleId: string;
  intent: 'approve' | 'reject';
  status: 'pending' | 'executing' | 'completed' | 'failed';
  result?: string;
  error?: string;
  onApprove: (id: string, feedback?: string) => void;
  onReject: (id: string) => void;
}

// ── Helper Functions ─────────────────────────────────────────────────────────

function formatArguments(args: Record<string, unknown>): Array<{ key: string; value: string }> {
  return Object.entries(args)
    .filter(([key]) => key !== 'action')
    .map(([key, value]) => ({
      key: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
      value: typeof value === 'string' ? value : JSON.stringify(value),
    }));
}

const REPAIR_COPY =
  'This module will be sent back for one repair attempt using your feedback. It will return here for another review — this is not final.';

const TERMINAL_COPY =
  'This permanently deletes the generated code, artifact bundle, and version history for this module. This cannot be undone. Add feedback instead to request a repair, or confirm to reject permanently.';

// ── Component ────────────────────────────────────────────────────────────────

export function ApprovalActionCard({
  toolCall,
  moduleId,
  intent,
  status,
  result,
  error,
  onApprove,
  onReject,
}: ApprovalActionCardProps) {
  const formattedArgs = formatArguments(toolCall.arguments);

  const [review, setReview] = useState<ModuleReview | null>(null);
  const [blueprintError, setBlueprintError] = useState<string | null>(null);
  const [loadingBlueprint, setLoadingBlueprint] = useState(true);

  const [feedback, setFeedback] = useState('');
  const [confirmingReject, setConfirmingReject] = useState(false);

  useEffect(() => {
    let ignore = false;
    setLoadingBlueprint(true);
    setBlueprintError(null);
    setReview(null);

    const [category, platform] = moduleId.split('/');
    if (!category || !platform) {
      setLoadingBlueprint(false);
      setBlueprintError(`Invalid module id: ${moduleId}`);
      return () => {
        ignore = true;
      };
    }

    adminApi
      .getModuleReview(category, platform)
      .then((data) => {
        if (ignore) return;
        setReview(data);
        setLoadingBlueprint(false);
      })
      .catch((err) => {
        if (ignore) return;
        setBlueprintError(err instanceof Error ? err.message : 'Failed to load module blueprint');
        setLoadingBlueprint(false);
      });

    return () => {
      ignore = true;
    };
  }, [moduleId]);

  // Reset the reject-confirmation flow whenever feedback becomes non-empty
  // (non-empty feedback is the reversible repair path — never destructive).
  useEffect(() => {
    if (feedback.trim().length > 0 && confirmingReject) {
      setConfirmingReject(false);
    }
  }, [feedback, confirmingReject]);

  const handleApproveClick = () => {
    onApprove(toolCall.id, feedback.trim() || undefined);
  };

  const handleRejectClick = () => {
    const trimmed = feedback.trim();
    if (trimmed.length > 0) {
      // Reversible repair path — single click, no confirmation needed (D-09).
      onReject(toolCall.id);
      return;
    }
    if (!confirmingReject) {
      setConfirmingReject(true);
      return;
    }
    // Second explicit click on empty feedback — terminal rejection.
    onReject(toolCall.id);
  };

  const rejectCopy = feedback.trim().length > 0 ? REPAIR_COPY : TERMINAL_COPY;

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3 max-w-md" data-approval-card>
      <style jsx>{`
        [data-approval-card] {
          container-type: inline-size;
          container-name: approval-card;
        }
        .approval-buttons-full {
          display: flex;
        }
        .approval-buttons-compact {
          display: none;
        }
        @container approval-card (max-width: 360px) {
          .approval-buttons-full {
            display: none;
          }
          .approval-buttons-compact {
            display: flex;
          }
        }
      `}</style>

      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-primary/10 p-2">
          <Puzzle className="w-4 h-4 text-primary" />
        </div>
        <div>
          <div className="text-sm font-semibold">
            Module {intent === 'approve' ? 'Approval' : 'Rejection'}: {moduleId}
          </div>
          <div className="text-xs text-muted-foreground">Module review requires confirmation</div>
        </div>
      </div>

      {/* Arguments */}
      {formattedArgs.length > 0 && (
        <div className="space-y-1.5 text-xs">
          {formattedArgs.map((arg) => (
            <div key={arg.key} className="flex gap-2">
              <span className="text-muted-foreground font-medium min-w-[80px]">{arg.key}:</span>
              <span className="text-foreground break-all">{arg.value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Blueprint summary — collapsed only (UI-SPEC Surface 5, no embedded React Flow graph in chat) */}
      {loadingBlueprint && (
        <div className="h-16 rounded-md border border-dashed border-zinc-600/50 bg-zinc-950/40 animate-pulse" />
      )}
      {!loadingBlueprint && blueprintError && (
        <DegradedBanner feature="Module blueprint" reasons={[blueprintError]} />
      )}
      {!loadingBlueprint && !blueprintError && review && (
        <BlueprintCard blueprint={review.blueprint} moduleName={moduleId} expandable={false} />
      )}

      {/* Optional feedback (pending only) */}
      {status === 'pending' && (
        <textarea
          value={feedback}
          onChange={(e) => setFeedback(e.target.value)}
          rows={2}
          placeholder="Optional: describe what to change…"
          className="w-full text-sm bg-zinc-950 border border-zinc-700 rounded-md p-2 text-foreground placeholder:text-muted-foreground"
        />
      )}

      {/* Status Area */}
      <AnimatePresence mode="wait">
        {status === 'pending' && (
          <motion.div
            key="pending"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="space-y-2"
          >
            {confirmingReject && feedback.trim().length === 0 && (
              <p className="text-xs text-red-400">{rejectCopy}</p>
            )}

            <div className="approval-buttons-full items-center gap-2">
              <button
                onClick={handleApproveClick}
                className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-green-500 hover:bg-green-600 text-white text-sm font-medium transition-colors"
              >
                <Check className="w-4 h-4" />
                Approve Module
              </button>
              <button
                onClick={handleRejectClick}
                className={`flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-white text-sm font-medium transition-colors ${
                  confirmingReject && feedback.trim().length === 0
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-red-500 hover:bg-red-600'
                }`}
              >
                <X className="w-4 h-4" />
                {confirmingReject && feedback.trim().length === 0 ? 'Confirm Reject' : 'Reject Module'}
              </button>
            </div>

            {/* Icon-only compact variant (<360px container width, WCAG 2.5.5 44px hit area) */}
            <div className="approval-buttons-compact items-center gap-2">
              <button
                onClick={handleApproveClick}
                aria-label="Approve Module"
                className="flex-1 flex items-center justify-center rounded-md bg-green-500 hover:bg-green-600 text-white transition-colors"
                style={{ minHeight: '44px', minWidth: '44px' }}
              >
                <Check className="w-5 h-5" />
              </button>
              <button
                onClick={handleRejectClick}
                aria-label="Reject Module"
                className={`flex-1 flex items-center justify-center rounded-md text-white transition-colors ${
                  confirmingReject && feedback.trim().length === 0
                    ? 'bg-red-600 hover:bg-red-700'
                    : 'bg-red-500 hover:bg-red-600'
                }`}
                style={{ minHeight: '44px', minWidth: '44px' }}
              >
                <X className="w-5 h-5" />
              </button>
            </div>
          </motion.div>
        )}

        {status === 'executing' && (
          <motion.div
            key="executing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <motion.div animate={{ rotate: 360 }} transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}>
              <Loader2 className="w-4 h-4" />
            </motion.div>
            Executing action...
          </motion.div>
        )}

        {status === 'completed' && (
          <motion.div
            key="completed"
            initial={{ scale: 0, opacity: 0 }}
            animate={{ scale: 1, opacity: 1, transition: { duration: 0.3, type: 'spring' } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="flex items-start gap-2 p-3 rounded-md bg-green-500/10 border border-green-500/20"
          >
            <Check className="w-4 h-4 text-green-500 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-green-500">
              <div className="font-medium">Action completed successfully</div>
              {result && <div className="opacity-90 mt-1">{result}</div>}
            </div>
          </motion.div>
        )}

        {status === 'failed' && (
          <motion.div
            key="failed"
            initial={{ scale: 0, opacity: 0 }}
            animate={{
              scale: 1,
              opacity: 1,
              x: [0, -10, 10, -10, 10, 0],
              transition: { duration: 0.5 },
            }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="flex items-start gap-2 p-3 rounded-md bg-red-500/10 border border-red-500/20"
          >
            <AlertTriangle className="w-4 h-4 text-red-500 mt-0.5 flex-shrink-0" />
            <div className="text-sm text-red-500">
              <div className="font-medium">Action failed</div>
              {error && <div className="opacity-90 mt-1">{error}</div>}
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      <Link href="/pipeline" className="text-orange-400 text-xs inline-block hover:text-orange-300 transition-colors">
        Open in Pipeline
      </Link>
    </div>
  );
}
