/**
 * AdapterCard Component
 *
 * Displays an adapter's status, name, and provides connect/disconnect actions.
 * Uses Framer Motion for layout animations and transitions.
 */
'use client';

import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Check, Lock, AlertCircle, Loader2, Zap } from 'lucide-react';
import type { AdapterCapability } from '@/lib/adminClient';

interface AdapterCardProps {
  adapter: AdapterCapability;
  onConnect: () => Promise<void>;
  onDisconnect: () => Promise<void>;
}

/**
 * Status badge color mapping
 */
const getStatusBadgeColor = (locked: boolean, lastTestOk: boolean | null): string => {
  if (!locked) {
    // Connected state
    return lastTestOk === false
      ? 'bg-red-500/10 text-red-400 border-red-500/30'  // Error
      : 'bg-green-500/10 text-green-400 border-green-500/30'; // Connected
  }
  // Locked state
  return 'bg-amber-500/10 text-amber-400 border-amber-500/30';
};

const getStatusLabel = (locked: boolean, lastTestOk: boolean | null): string => {
  if (!locked) {
    return lastTestOk === false ? 'Error' : 'Connected';
  }
  return 'Locked';
};

const getStatusIcon = (locked: boolean, lastTestOk: boolean | null) => {
  if (locked) return Lock;
  if (lastTestOk === false) return AlertCircle;
  return Check;
};

/**
 * Format timestamp for display
 */
const formatTimestamp = (timestamp: string | null): string => {
  if (!timestamp) return 'Not configured';

  const date = new Date(timestamp);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffMins = Math.floor(diffMs / 60000);

  if (diffMins < 1) return 'Just now';
  if (diffMins < 60) return `${diffMins} min ago`;
  if (diffMins < 1440) return `${Math.floor(diffMins / 60)} hr ago`;
  return date.toLocaleDateString();
};

export function AdapterCard({ adapter, onConnect, onDisconnect }: AdapterCardProps) {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleAction = async () => {
    setIsLoading(true);
    setError(null);

    try {
      if (adapter.locked) {
        await onConnect();
      } else {
        await onDisconnect();
      }
    } catch (err: any) {
      setError(err.message || 'Action failed');
      console.error('Adapter action error:', err);
    } finally {
      setIsLoading(false);
    }
  };

  const StatusIcon = getStatusIcon(adapter.locked, adapter.last_test_ok);
  const shouldPulse = !adapter.locked && adapter.last_test_ok === false;

  return (
    <motion.div
      layout
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      exit={{ opacity: 0, scale: 0.95 }}
      transition={{ duration: 0.2 }}
      className="relative flex flex-col p-4 rounded-xl border border-gray-700 bg-gray-800/50 hover:border-gray-600 hover:bg-gray-800/70 transition-all"
    >
      {/* Status Badge */}
      <div className="flex items-center justify-between mb-3">
        <div
          className={`flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border ${getStatusBadgeColor(
            adapter.locked,
            adapter.last_test_ok
          )}`}
        >
          <StatusIcon className="w-3 h-3" />
          {getStatusLabel(adapter.locked, adapter.last_test_ok)}
        </div>

        {/* Connection test indicator */}
        {adapter.connection_tested && (
          <motion.div
            animate={shouldPulse ? { scale: [1, 1.2, 1], opacity: [1, 0.5, 1] } : {}}
            transition={shouldPulse ? { duration: 1.5, repeat: Infinity } : {}}
            className={`w-2 h-2 rounded-full ${
              adapter.last_test_ok === false ? 'bg-red-400' : 'bg-green-400'
            }`}
            title={adapter.last_test_ok === false ? 'Connection test failed' : 'Connection test passed'}
          />
        )}
      </div>

      {/* Adapter Info */}
      <div className="flex items-start gap-3 mb-3">
        <div className="flex items-center justify-center w-10 h-10 rounded-lg bg-gradient-to-br from-blue-600 to-cyan-500">
          <Zap className="w-5 h-5 text-white" />
        </div>

        <div className="flex-1 min-w-0">
          <h3 className="font-semibold text-sm text-white truncate">{adapter.name}</h3>
          <p className="text-xs text-gray-400 capitalize">{adapter.category}</p>
        </div>
      </div>

      {/* Last Data Timestamp */}
      <p className="text-xs text-gray-500 mb-3">
        {adapter.locked ? (
          <span>
            Missing: <span className="text-amber-400">{adapter.missing_fields.join(', ')}</span>
          </span>
        ) : (
          `Last data: ${formatTimestamp(adapter.last_data_timestamp)}`
        )}
      </p>

      {/* Error Message */}
      {error && (
        <motion.div
          initial={{ opacity: 0, height: 0 }}
          animate={{ opacity: 1, height: 'auto' }}
          className="mb-2 p-2 bg-red-500/10 border border-red-500/30 rounded-lg text-xs text-red-400"
        >
          {error}
        </motion.div>
      )}

      {/* Action Button */}
      <button
        onClick={handleAction}
        disabled={isLoading}
        className={`flex items-center justify-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${
          adapter.locked
            ? 'bg-blue-600 hover:bg-blue-500 text-white'
            : 'bg-red-500/10 hover:bg-red-500/20 text-red-400'
        }`}
      >
        {isLoading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            {adapter.locked ? 'Testing...' : 'Disconnecting...'}
          </>
        ) : (
          <>
            {adapter.locked ? 'Connect' : 'Disconnect'}
          </>
        )}
      </button>
    </motion.div>
  );
}
