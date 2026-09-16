'use client';

/**
 * RewindToast — transient rewind confirmation (Phase 9 plan 09,
 * 09-UI-SPEC.md Component Contracts §5).
 *
 * Fires only when a "Reject Change" action actually rewinds applied state
 * (clear-then-restore, per the LOCKED history decision) — a reject of a
 * merely-staged proposal shows the panel's inline state instead and never
 * renders this toast. No toast library is installed; this is a single
 * hand-rolled component per 09-RESEARCH.md's Don't-Hand-Roll guidance, which
 * scopes to ECS-internal serialization/dirty-tracking, not general UI
 * feedback.
 */

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { RotateCcw } from 'lucide-react';

interface RewindToastProps {
  message: string | null;
  onDismiss: () => void;
}

export function RewindToast({ message, onDismiss }: RewindToastProps) {
  React.useEffect(() => {
    if (!message) return;
    const timer = setTimeout(onDismiss, 3000);
    return () => clearTimeout(timer);
  }, [message, onDismiss]);

  return (
    <AnimatePresence>
      {message && (
        <motion.div
          key="rewind-toast"
          initial={{ opacity: 0, y: -8 }}
          animate={{ opacity: 1, y: 0 }}
          exit={{ opacity: 0, y: -8 }}
          className="fixed top-4 left-1/2 -translate-x-1/2 bg-zinc-800 border border-zinc-700 rounded-md px-3 py-2 shadow-lg z-[60] flex items-center gap-2"
        >
          <RotateCcw className="w-3.5 h-3.5 text-zinc-400" />
          <span className="text-sm text-zinc-200">{message}</span>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
