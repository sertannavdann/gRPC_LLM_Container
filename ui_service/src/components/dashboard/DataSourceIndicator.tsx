/**
 * DataSourceIndicator Component
 *
 * Animated pill indicator showing Live/Mock/Offline status.
 * Uses Framer Motion for smooth state transitions.
 * Derives status from XState nexusAppMachine dataSource parallel region.
 */
'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';

interface DataSourceIndicatorProps {
  status: 'live' | 'mock' | 'offline' | 'unknown';
}

/**
 * Status configuration mapping
 */
const STATUS_CONFIG = {
  live: {
    label: 'Live',
    dotColor: 'bg-green-400',
    textColor: 'text-green-400',
    bgColor: 'bg-green-500/10',
    borderColor: 'border-green-500/30',
    pulse: true,
  },
  mock: {
    label: 'Mock',
    dotColor: 'bg-amber-400',
    textColor: 'text-amber-400',
    bgColor: 'bg-amber-500/10',
    borderColor: 'border-amber-500/30',
    pulse: false,
  },
  offline: {
    label: 'Offline',
    dotColor: 'bg-red-400',
    textColor: 'text-red-400',
    bgColor: 'bg-red-500/10',
    borderColor: 'border-red-500/30',
    pulse: false,
  },
  unknown: {
    label: 'Unknown',
    dotColor: 'bg-gray-400',
    textColor: 'text-gray-400',
    bgColor: 'bg-gray-500/10',
    borderColor: 'border-gray-500/30',
    pulse: false,
  },
} as const;

export function DataSourceIndicator({ status }: DataSourceIndicatorProps) {
  const config = STATUS_CONFIG[status];

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={status}
        layout
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        exit={{ opacity: 0, scale: 0.8 }}
        transition={{ duration: 0.3, ease: 'easeInOut' }}
        className={`flex items-center gap-2 px-3 py-1.5 rounded-full border ${config.bgColor} ${config.borderColor}`}
      >
        {/* Status Dot with optional pulse animation */}
        <motion.div
          animate={
            config.pulse
              ? {
                  scale: [1, 1.4, 1],
                  opacity: [1, 0.5, 1],
                }
              : {}
          }
          transition={
            config.pulse
              ? {
                  duration: 2,
                  repeat: Infinity,
                  ease: 'easeInOut',
                }
              : {}
          }
          className={`w-2 h-2 rounded-full ${config.dotColor}`}
        />

        {/* Status Label */}
        <span className={`text-sm font-medium ${config.textColor}`}>
          {config.label}
        </span>
      </motion.div>
    </AnimatePresence>
  );
}
