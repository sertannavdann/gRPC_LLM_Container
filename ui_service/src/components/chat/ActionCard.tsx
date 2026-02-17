/**
 * ActionCard Component
 *
 * Chat action confirmation card for adapter tool calls with human-in-the-loop approval.
 * Displays tool call details with approve/reject buttons and animated state transitions.
 *
 * States:
 *   - pending: Show approve/reject buttons
 *   - executing: Show spinner animation
 *   - completed: Show green check with result
 *   - failed: Show red warning with error message
 *
 * Uses Framer Motion for smooth state transitions.
 * Parses tool names (e.g., "calendar.create_event" -> "Calendar: Create Event")
 */

'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  Check,
  X,
  Loader2,
  AlertTriangle,
  Calendar,
  Cloud,
  DollarSign,
  Gamepad2,
  Wrench,
} from 'lucide-react';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ToolCall {
  id: string;
  name: string;
  arguments: Record<string, unknown>;
}

export interface ActionCardProps {
  toolCall: ToolCall;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  status: 'pending' | 'executing' | 'completed' | 'failed';
  result?: string;
  error?: string;
}

// ── Helper Functions ─────────────────────────────────────────────────────────

function parseToolName(name: string): { category: string; action: string; icon: React.ElementType } {
  const parts = name.split('.');
  const category = parts[0] || 'tool';
  const action = parts
    .slice(1)
    .join(' ')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase());

  // Icon mapping
  const iconMap: Record<string, React.ElementType> = {
    calendar: Calendar,
    weather: Cloud,
    finance: DollarSign,
    gaming: Gamepad2,
  };

  return {
    category: category.charAt(0).toUpperCase() + category.slice(1),
    action: action || 'Execute',
    icon: iconMap[category.toLowerCase()] || Wrench,
  };
}

function formatArguments(args: Record<string, unknown>): Array<{ key: string; value: string }> {
  return Object.entries(args).map(([key, value]) => ({
    key: key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
    value: typeof value === 'string' ? value : JSON.stringify(value),
  }));
}

// ── Component ────────────────────────────────────────────────────────────────

export function ActionCard({
  toolCall,
  onApprove,
  onReject,
  status,
  result,
  error,
}: ActionCardProps) {
  const { category, action, icon: Icon } = parseToolName(toolCall.name);
  const formattedArgs = formatArguments(toolCall.arguments);

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3 max-w-md">
      {/* Header */}
      <div className="flex items-center gap-3">
        <div className="rounded-full bg-primary/10 p-2">
          <Icon className="w-4 h-4 text-primary" />
        </div>
        <div>
          <div className="text-sm font-semibold">
            {category}: {action}
          </div>
          <div className="text-xs text-muted-foreground">Tool action requires confirmation</div>
        </div>
      </div>

      {/* Arguments */}
      {formattedArgs.length > 0 && (
        <div className="space-y-1.5 text-xs">
          {formattedArgs.map((arg) => (
            <div key={arg.key} className="flex gap-2">
              <span className="text-muted-foreground font-medium min-w-[80px]">
                {arg.key}:
              </span>
              <span className="text-foreground break-all">{arg.value}</span>
            </div>
          ))}
        </div>
      )}

      {/* Status Area */}
      <AnimatePresence mode="wait">
        {/* Pending: Show approve/reject buttons */}
        {status === 'pending' && (
          <motion.div
            key="pending"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="flex items-center gap-2"
          >
            <button
              onClick={() => onApprove(toolCall.id)}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-green-500 hover:bg-green-600 text-white text-sm font-medium transition-colors"
            >
              <Check className="w-4 h-4" />
              Approve
            </button>
            <button
              onClick={() => onReject(toolCall.id)}
              className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md bg-red-500 hover:bg-red-600 text-white text-sm font-medium transition-colors"
            >
              <X className="w-4 h-4" />
              Reject
            </button>
          </motion.div>
        )}

        {/* Executing: Show spinner */}
        {status === 'executing' && (
          <motion.div
            key="executing"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1, transition: { duration: 0.2 } }}
            exit={{ opacity: 0, transition: { duration: 0.1 } }}
            className="flex items-center gap-2 text-sm text-muted-foreground"
          >
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1, ease: 'linear' }}
            >
              <Loader2 className="w-4 h-4" />
            </motion.div>
            Executing action...
          </motion.div>
        )}

        {/* Completed: Show green check */}
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

        {/* Failed: Show red warning with shake */}
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
    </div>
  );
}
