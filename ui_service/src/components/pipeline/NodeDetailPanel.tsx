/**
 * NodeDetailPanel — Slide-out detail panel for pipeline nodes.
 * Shows node details, status, and test runner for adapter nodes.
 */
'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  X,
  Workflow,
  Wrench,
  Database,
  Lock,
  Unlock,
  Play,
  Loader2,
  CheckCircle2,
  XCircle,
} from 'lucide-react';
import type { TestRunResult } from '@/lib/adminClient';
import type { SelectedNode } from '@/store/nexusStore';

interface NodeDetailPanelProps {
  node: SelectedNode | null;
  onClose: () => void;
  testRunning: boolean;
  testResult: TestRunResult | null;
  onRunTests?: (category: string, platform: string) => void;
}

const typeConfig: Record<string, { icon: React.ReactNode; color: string; label: string }> = {
  stage: {
    icon: <Workflow className="w-4 h-4 text-orange-400" />,
    color: 'text-orange-400',
    label: 'Pipeline Stage',
  },
  tool: {
    icon: <Wrench className="w-4 h-4 text-amber-400" />,
    color: 'text-amber-400',
    label: 'Tool',
  },
  adapter: {
    icon: <Database className="w-4 h-4 text-blue-400" />,
    color: 'text-blue-400',
    label: 'Adapter',
  },
  service: {
    icon: <Workflow className="w-4 h-4 text-green-400" />,
    color: 'text-green-400',
    label: 'Service',
  },
};

function StatusDot({ state }: { state: string }) {
  const colors: Record<string, string> = {
    running: 'bg-green-400',
    error: 'bg-red-400',
    disabled: 'bg-zinc-500',
    idle: 'bg-zinc-500',
    locked: 'bg-yellow-400',
  };
  return <span className={`w-2 h-2 rounded-full ${colors[state] ?? 'bg-zinc-500'}`} />;
}

export function NodeDetailPanel({
  node,
  onClose,
  testRunning,
  testResult,
  onRunTests,
}: NodeDetailPanelProps) {
  const d = node?.data ?? {};
  const cfg = typeConfig[node?.type ?? ''] ?? typeConfig.stage;

  // Extract typed values from data record
  const label = (d.label as string) ?? node?.id ?? '';
  const state = (d.state as string) ?? '';
  const category = (d.category as string) ?? '';
  const platform = (d.platform as string) ?? '';
  const stage = (d.stage as string) ?? '';
  const description = (d.description as string) ?? '';
  const latencyMs = (d.latency_ms as number) ?? 0;
  const connectedAdapters = (d.connectedAdapters as string[]) ?? [];
  const requiresAuth = Boolean(d.requiresAuth);
  const hasCredentials = Boolean(d.hasCredentials);

  // Adapter-specific
  const isAdapter = node?.type === 'adapter';
  const adapterId = (d.adapterId as string) ?? '';
  const [adapterCat, adapterPlat] = adapterId ? adapterId.split('/') : ['', ''];
  const locked = isAdapter && requiresAuth && !hasCredentials;

  return (
    <AnimatePresence>
      {node && (
        <>
          {/* Backdrop */}
          <motion.div
            key="backdrop"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 bg-black/30 z-40"
            onClick={onClose}
          />

          {/* Panel */}
          <motion.div
            key="panel"
            initial={{ x: '100%' }}
            animate={{ x: 0 }}
            exit={{ x: '100%' }}
            transition={{ type: 'spring', damping: 25, stiffness: 300 }}
            className="fixed right-0 top-0 bottom-0 w-96 bg-zinc-900 border-l border-zinc-700 z-50 flex flex-col shadow-2xl"
          >
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b border-zinc-700">
              <div className="flex items-center gap-2">
                {cfg.icon}
                <span className="text-sm font-semibold text-zinc-100">
                  {label}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] px-2 py-0.5 rounded-full bg-zinc-800 ${cfg.color}`}>
                  {cfg.label}
                </span>
                <button
                  onClick={onClose}
                  className="p-1 rounded hover:bg-zinc-700 transition-colors"
                >
                  <X className="w-4 h-4 text-zinc-400" />
                </button>
              </div>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-auto p-4 space-y-4">
              {/* Status section */}
              <section>
                <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                  Status
                </h3>
                <div className="space-y-2">
                  {state && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">State</span>
                      <span className="flex items-center gap-1.5 text-zinc-200">
                        <StatusDot state={locked ? 'locked' : state} />
                        {locked ? 'Locked' : state}
                      </span>
                    </div>
                  )}
                  {category && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Category</span>
                      <span className="text-zinc-200">{category}</span>
                    </div>
                  )}
                  {platform && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Platform</span>
                      <span className="text-zinc-200">{platform}</span>
                    </div>
                  )}
                  {stage && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Stage</span>
                      <span className="text-zinc-200">{stage}</span>
                    </div>
                  )}
                  {description && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Description</span>
                      <span className="text-zinc-200">{description}</span>
                    </div>
                  )}
                  {latencyMs > 0 && (
                    <div className="flex items-center justify-between text-sm">
                      <span className="text-zinc-400">Latency</span>
                      <span className="text-zinc-200">{latencyMs}ms</span>
                    </div>
                  )}
                </div>
              </section>

              {/* Auth section (adapters only) */}
              {isAdapter && (
                <section>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Authentication
                  </h3>
                  <div className="flex items-center gap-2 text-sm">
                    {locked ? (
                      <>
                        <Lock className="w-4 h-4 text-yellow-400" />
                        <span className="text-yellow-300">Credentials required</span>
                      </>
                    ) : requiresAuth ? (
                      <>
                        <Unlock className="w-4 h-4 text-green-400" />
                        <span className="text-green-300">Authenticated</span>
                      </>
                    ) : (
                      <span className="text-zinc-400">No authentication required</span>
                    )}
                  </div>
                </section>
              )}

              {/* Connected items */}
              {node.type === 'tool' && connectedAdapters.length > 0 && (
                <section>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Connected Adapters
                  </h3>
                  <div className="space-y-1">
                    {connectedAdapters.map((id) => (
                      <div
                        key={id}
                        className="text-xs text-zinc-300 px-2 py-1 rounded bg-zinc-800/60"
                      >
                        {id}
                      </div>
                    ))}
                  </div>
                </section>
              )}

              {/* Test runner (adapters only) */}
              {isAdapter && adapterCat && adapterPlat && (
                <section>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Test Runner
                  </h3>
                  <button
                    onClick={() => onRunTests?.(adapterCat, adapterPlat)}
                    disabled={testRunning}
                    className="flex items-center gap-2 px-3 py-2 rounded-md text-sm font-medium bg-blue-600 hover:bg-blue-500 disabled:bg-zinc-700 disabled:text-zinc-500 text-white transition-colors w-full justify-center"
                  >
                    {testRunning ? (
                      <>
                        <Loader2 className="w-4 h-4 animate-spin" />
                        Running tests...
                      </>
                    ) : (
                      <>
                        <Play className="w-4 h-4" />
                        Run Tests
                      </>
                    )}
                  </button>

                  {/* Test results */}
                  {testResult && (
                    <div className="mt-3 space-y-2">
                      <div className="flex items-center gap-2">
                        {testResult.exit_code === 0 ? (
                          <CheckCircle2 className="w-4 h-4 text-green-400" />
                        ) : (
                          <XCircle className="w-4 h-4 text-red-400" />
                        )}
                        <span
                          className={`text-sm font-medium ${
                            testResult.exit_code === 0 ? 'text-green-300' : 'text-red-300'
                          }`}
                        >
                          {testResult.exit_code === 0 ? 'All tests passed' : 'Tests failed'}
                        </span>
                        <span className="text-[10px] text-zinc-500 ml-auto">
                          {testResult.duration_ms.toFixed(0)}ms
                        </span>
                      </div>

                      <div className="flex items-center gap-3 text-xs">
                        <span className="text-green-400">
                          {testResult.tests_passed} passed
                        </span>
                        {testResult.tests_failed > 0 && (
                          <span className="text-red-400">
                            {testResult.tests_failed} failed
                          </span>
                        )}
                        <span className="text-zinc-500">
                          {testResult.tests_total} total
                        </span>
                      </div>

                      {/* Stdout output */}
                      {testResult.stdout && (
                        <pre className="text-[11px] text-zinc-400 bg-zinc-950 rounded p-2 overflow-auto max-h-60 whitespace-pre-wrap font-mono">
                          {testResult.stdout}
                        </pre>
                      )}

                      {/* Stderr output */}
                      {testResult.stderr && (
                        <pre className="text-[11px] text-red-400/80 bg-zinc-950 rounded p-2 overflow-auto max-h-40 whitespace-pre-wrap font-mono">
                          {testResult.stderr}
                        </pre>
                      )}
                    </div>
                  )}
                </section>
              )}
            </div>
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
