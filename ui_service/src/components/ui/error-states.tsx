/**
 * Error State Components
 *
 * Three animated error state components with Framer Motion:
 * - DegradedBanner: amber banner for DEGRADED features, optional retry
 * - EmptyState: centered placeholder for no-data states
 * - TimeoutSkeleton: skeleton with "Taking longer..." overlay after 5s
 *
 * Uses shadcn/ui primitives (Alert styles, Skeleton, Button patterns).
 * Driven by NexusErrorType classification from XState guards.
 */

'use client';

import React, { useState, useEffect } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, RefreshCw, Inbox, Clock } from 'lucide-react';

// ── DegradedBanner ──────────────────────────────────────────────────────────

interface DegradedBannerProps {
  feature: string;
  reasons: string[];
  onRetry?: () => void;
}

/**
 * Amber warning banner shown when a feature is in DEGRADED state.
 * Animates in from top with opacity + y transition.
 */
export function DegradedBanner({ feature, reasons, onRetry }: DegradedBannerProps) {
  return (
    <AnimatePresence>
      <motion.div
        initial={{ opacity: 0, y: -10 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -10 }}
        transition={{ duration: 0.3, ease: 'easeOut' }}
        className="flex items-start gap-3 px-4 py-3 bg-amber-500/10 border border-amber-500/30 rounded-lg"
        role="alert"
      >
        <AlertTriangle className="w-5 h-5 text-amber-400 flex-shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-amber-300">
            {feature} is degraded
          </p>
          {reasons.length > 0 && (
            <ul className="mt-1 text-xs text-amber-400/80 space-y-0.5">
              {reasons.map((reason, i) => (
                <li key={i}>{reason}</li>
              ))}
            </ul>
          )}
        </div>
        {onRetry && (
          <button
            onClick={onRetry}
            className="flex items-center gap-1 px-2.5 py-1 text-xs font-medium text-amber-300 bg-amber-500/20 hover:bg-amber-500/30 rounded-md transition-colors flex-shrink-0"
          >
            <RefreshCw className="w-3 h-3" />
            Retry
          </button>
        )}
      </motion.div>
    </AnimatePresence>
  );
}

// ── EmptyState ──────────────────────────────────────────────────────────────

interface EmptyStateProps {
  title: string;
  description: string;
  action?: {
    label: string;
    onClick: () => void;
  };
}

/**
 * Centered empty state with optional action button.
 * Scales in from 0.9 with opacity transition.
 */
export function EmptyState({ title, description, action }: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.9 }}
      animate={{ opacity: 1, scale: 1 }}
      transition={{ duration: 0.3, ease: 'easeOut' }}
      className="flex flex-col items-center justify-center py-12 px-6 text-center"
    >
      <div className="flex items-center justify-center w-16 h-16 rounded-full bg-muted/50 mb-4">
        <Inbox className="w-8 h-8 text-muted-foreground" />
      </div>
      <h3 className="text-lg font-medium text-foreground mb-1.5">{title}</h3>
      <p className="text-sm text-muted-foreground max-w-sm mb-4">{description}</p>
      {action && (
        <button
          onClick={action.onClick}
          className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium bg-primary text-primary-foreground rounded-md hover:bg-primary/90 transition-colors"
        >
          {action.label}
        </button>
      )}
    </motion.div>
  );
}

// ── TimeoutSkeleton ─────────────────────────────────────────────────────────

interface TimeoutSkeletonProps {
  children: React.ReactNode;
  delayMs?: number;
}

/**
 * Wraps skeleton/loading UI with a "Taking longer than usual..." overlay
 * that appears after a configurable delay (default 5s).
 */
export function TimeoutSkeleton({ children, delayMs = 5000 }: TimeoutSkeletonProps) {
  const [showTimeout, setShowTimeout] = useState(false);

  useEffect(() => {
    const timer = setTimeout(() => setShowTimeout(true), delayMs);
    return () => clearTimeout(timer);
  }, [delayMs]);

  return (
    <div className="relative">
      {children}

      <AnimatePresence>
        {showTimeout && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.4 }}
            className="absolute inset-0 flex items-center justify-center bg-background/60 backdrop-blur-[2px] rounded-lg"
          >
            <div className="flex items-center gap-2 px-4 py-2.5 bg-card border border-border rounded-lg shadow-md">
              <Clock className="w-4 h-4 text-muted-foreground animate-pulse" />
              <span className="text-sm text-muted-foreground">
                Taking longer than usual...
              </span>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
