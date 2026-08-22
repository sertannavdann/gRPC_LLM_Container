/**
 * NodeDetailPanel — Slide-out detail panel for pipeline nodes.
 * Shows node details, status, and test runner for adapter nodes.
 *
 * Module review surface (D-06/D-05/D-08/D-15, REQ-014): when the selected
 * node is a module carrying `pendingApproval: true`, the content area also
 * renders the LLM-generated walkthrough (D-08), five collapsible review
 * sections (blueprint/diff/sandbox/credentials/repair-history, D-06), and a
 * sticky approve/reject footer (D-09) below the scroll area.
 */
'use client';

import React from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import * as Accordion from '@radix-ui/react-accordion';
import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
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
  Puzzle,
  Sparkles,
  ChevronDown,
  LayoutTemplate,
  GitCompare,
  FlaskConical,
  KeyRound,
  History,
  Check,
} from 'lucide-react';
import type { TestRunResult, ModuleReview, ModuleAuditAttempt } from '@/lib/adminClient';
import type { SelectedNode } from '@/store/nexusStore';
import { BlueprintCard } from './BlueprintCard';
import { ModulePanel } from './ModulePanel';
import { DegradedBanner } from '@/components/ui/error-states';

interface NodeDetailPanelProps {
  node: SelectedNode | null;
  onClose: () => void;
  testRunning: boolean;
  testResult: TestRunResult | null;
  onRunTests?: (category: string, platform: string) => void;
  // Module review surface (Phase 8 plan 08-09)
  review?: ModuleReview | null;
  audit?: ModuleAuditAttempt[];
  reviewState?: string;
  actionError?: string | null;
  onApprove?: () => void;
  onReject?: (feedback?: string) => void;
  onRetryReview?: () => void;
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
  module: {
    icon: <Puzzle className="w-4 h-4 text-amber-400" />,
    color: 'text-amber-400',
    label: 'Module',
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

// ── Repair-history stage colors — reused verbatim from PipelineStageFlow.tsx /
//    ModuleNode.tsx (UI-SPEC §4 forbids redefining these). ─────────────────────

const STAGE_COLORS: Record<string, { border: string; bg: string; text: string }> = {
  scaffold: { border: '#3b82f6', bg: 'bg-blue-500/10', text: 'text-blue-400' },
  implement: { border: '#8b5cf6', bg: 'bg-purple-500/10', text: 'text-purple-400' },
  test: { border: '#f59e0b', bg: 'bg-amber-500/10', text: 'text-amber-400' },
  repair: { border: '#ef4444', bg: 'bg-red-500/10', text: 'text-red-400' },
};

/** Explicit tests(plural, AttemptRecord.stage) -> test(singular, STAGE_COLORS) mapping. */
function stageColorKey(stage: string): string {
  return stage === 'tests' ? 'test' : stage;
}

// ── Accordion section wrapper — shared trigger/content chrome for the five
//    review layers (D-06). ──────────────────────────────────────────────────

/**
 * Shared trigger/content chrome for a review section. Callers wrap this in
 * their own `<Accordion.Item value="...">` (five distinct literal usages
 * below — one per D-06 review layer) rather than this helper owning the
 * Item itself, so each of the five sections is independently addressable.
 */
function AccordionSectionBody({
  icon,
  label,
  children,
}: {
  icon: React.ReactNode;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <>
      <Accordion.Header>
        <Accordion.Trigger className="group flex items-center justify-between w-full px-3 py-2.5 text-xs font-medium text-zinc-400 uppercase tracking-wide hover:text-zinc-200 transition-colors">
          <span className="flex items-center gap-2">
            {icon}
            {label}
          </span>
          <ChevronDown className="w-3.5 h-3.5 transition-transform group-data-[state=open]:rotate-180" />
        </Accordion.Trigger>
      </Accordion.Header>
      <Accordion.Content className="overflow-hidden data-[state=open]:animate-accordion-down data-[state=closed]:animate-accordion-up">
        <div className="px-3 pb-3">{children}</div>
      </Accordion.Content>
    </>
  );
}

// ── Sandbox validation report shape (shared/modules/validation_types.py
//    ValidationResult.to_dict()) — review.validation_results is typed loosely
//    as Record<string, unknown> in adminClient.ts, narrowed here at render time. ──

interface ValidationEntryShape {
  severity: string;
  category: string;
  message: string;
}

interface ValidationResultShape {
  passed?: boolean;
  entries?: ValidationEntryShape[];
  summary?: string;
}

export function NodeDetailPanel({
  node,
  onClose,
  testRunning,
  testResult,
  onRunTests,
  review,
  audit = [],
  reviewState,
  actionError,
  onApprove,
  onReject,
  onRetryReview,
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

  // Module review surface (D-06/D-05/D-08/D-15)
  const isModule = node?.type === 'module';
  const pendingApproval = Boolean(d.pendingApproval);
  const showReviewSurface = isModule && pendingApproval;

  // Auto-generated module output panel (D-07, plan 08-12) — mutually
  // exclusive with the review surface above: a module is either awaiting
  // approval (review surface) or has an output surface (this), never both.
  const moduleId = (d.moduleId as string) ?? '';
  const moduleStatus = (d.status as string) ?? '';
  const isModuleInstalled = moduleStatus === 'installed' || state === 'running';
  const showModulePanel = isModule && !pendingApproval && isModuleInstalled && Boolean(moduleId);
  const showModuleUnavailableNotice = isModule && !pendingApproval && !isModuleInstalled;

  const [rejectFeedback, setRejectFeedback] = React.useState('');
  const [confirmingReject, setConfirmingReject] = React.useState(false);

  // Reset reject flow state whenever the selected node changes so a stale
  // "Confirm Reject" state never leaks across modules.
  React.useEffect(() => {
    setRejectFeedback('');
    setConfirmingReject(false);
  }, [node?.id]);

  const busy = reviewState === 'approving' || reviewState === 'rejecting';
  const rejectLabel = confirmingReject && !rejectFeedback.trim() ? 'Confirm Reject' : 'Reject Module';

  const handleRejectClick = () => {
    const feedback = rejectFeedback.trim();
    if (feedback) {
      onReject?.(feedback);
      return;
    }
    if (confirmingReject) {
      onReject?.(undefined);
      setConfirmingReject(false);
      return;
    }
    setConfirmingReject(true);
  };

  const validation = review?.validation_results as ValidationResultShape | undefined;

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

              {/* Auto-generated module output panel (D-07) — installed,
                  non-pending modules only; the review surface above owns
                  pending-approval modules exclusively. */}
              {showModulePanel && <ModulePanel moduleId={moduleId} />}

              {/* Explicit status line for modules with neither a review
                  surface nor an output surface (e.g. failed, validating) —
                  Phase 6 no-silent-fallback: the panel body must never be
                  left blank for a module node. */}
              {showModuleUnavailableNotice && (
                <section>
                  <h3 className="text-xs font-medium text-zinc-400 uppercase tracking-wide mb-2">
                    Module Output
                  </h3>
                  <p className="text-xs text-zinc-500">
                    {moduleStatus === 'failed' || moduleStatus === 'rejected'
                      ? 'This module failed validation and has no output surface.'
                      : moduleStatus === 'validating' || moduleStatus === 'pending'
                        ? 'This module is still being validated — no output surface yet.'
                        : `No output surface available for this module (status: ${moduleStatus || 'unknown'}).`}
                  </p>
                </section>
              )}

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

              {/* ── Module review surface (D-06/D-05/D-08/D-15, REQ-014) ── */}
              {showReviewSurface && (
                <>
                  {reviewState === 'loading' && (
                    <div className="flex items-center justify-center py-8">
                      <Loader2 className="w-5 h-5 text-zinc-500 animate-spin" />
                    </div>
                  )}

                  {reviewState === 'error' && (
                    <DegradedBanner
                      feature="Module review"
                      reasons={[
                        actionError ??
                          "Couldn't load the validation report. Check the repair-history timeline for the last known state.",
                      ]}
                      onRetry={onRetryReview}
                    />
                  )}

                  {review && (reviewState === 'open' || reviewState === 'approving' || reviewState === 'rejecting') && (
                    <>
                      {/* Walkthrough block (D-08) — displayed above the accordion */}
                      {review.walkthrough && (
                        <div className="rounded-lg border border-violet-500/30 bg-violet-500/5 p-3">
                          <div className="flex items-center gap-1.5 mb-2">
                            <Sparkles className="w-3 h-3 text-violet-400" />
                            <span className="text-xs font-semibold text-violet-300 uppercase tracking-wide">
                              How this module works
                            </span>
                          </div>
                          <div className="text-sm text-zinc-300 prose prose-sm prose-invert max-w-none">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                              {review.walkthrough}
                            </ReactMarkdown>
                          </div>
                        </div>
                      )}

                      {/* Five collapsible review sections (D-06) */}
                      <Accordion.Root
                        type="multiple"
                        defaultValue={['blueprint']}
                        className="border border-zinc-800 rounded-lg overflow-hidden"
                      >
                        <Accordion.Item value="blueprint" className="border-b border-zinc-800 last:border-b-0">
                          <AccordionSectionBody
                            icon={<LayoutTemplate className="w-3.5 h-3.5" />}
                            label="Blueprint"
                          >
                            {review.blueprint ? (
                              <BlueprintCard blueprint={review.blueprint} moduleName={label} />
                            ) : (
                              <p className="text-xs text-zinc-500">No blueprint data available.</p>
                            )}
                          </AccordionSectionBody>
                        </Accordion.Item>

                        <Accordion.Item value="code-diff" className="border-b border-zinc-800 last:border-b-0">
                          <AccordionSectionBody
                            icon={<GitCompare className="w-3.5 h-3.5" />}
                            label="Code Diff"
                          >
                            {/* Path A (freshly built, no draft) has no diff source — the
                                review payload never carries one. Path B dev-mode drafts
                                keep their existing draft-diff endpoint/RBAC gate,
                                intentionally out of scope for this review surface
                                (RESEARCH.md Open Question Q1). */}
                            <div className="text-[11px] text-zinc-500 bg-zinc-950 border border-zinc-800 rounded p-2 font-mono">
                              No draft diff — this module was built fresh. A diff becomes
                              available once a dev-mode draft is created from an installed
                              version.
                            </div>
                          </AccordionSectionBody>
                        </Accordion.Item>

                        <Accordion.Item value="validation" className="border-b border-zinc-800 last:border-b-0">
                          <AccordionSectionBody
                            icon={<FlaskConical className="w-3.5 h-3.5" />}
                            label="Sandbox Validation Report"
                          >
                          {validation ? (
                            <div className="space-y-2">
                              <div className="flex items-center gap-2 text-sm">
                                {validation.passed ? (
                                  <CheckCircle2 className="w-4 h-4 text-green-400" />
                                ) : (
                                  <XCircle className="w-4 h-4 text-red-400" />
                                )}
                                <span
                                  className={
                                    validation.passed ? 'text-green-300' : 'text-red-300'
                                  }
                                >
                                  {validation.passed ? 'Validation passed' : 'Validation failed'}
                                </span>
                              </div>
                              {validation.summary && (
                                <p className="text-xs text-zinc-400">{validation.summary}</p>
                              )}
                              {(validation.entries ?? []).length > 0 && (
                                <div className="space-y-1">
                                  {(validation.entries ?? []).map((entry, i) => (
                                    <div key={i} className="flex items-start gap-2 text-xs">
                                      {entry.severity === 'error' ? (
                                        <XCircle className="w-3.5 h-3.5 text-red-400 mt-0.5 flex-shrink-0" />
                                      ) : (
                                        <CheckCircle2 className="w-3.5 h-3.5 text-green-400 mt-0.5 flex-shrink-0" />
                                      )}
                                      <span className="text-zinc-300">
                                        <span className="text-zinc-500">[{entry.category}]</span>{' '}
                                        {entry.message}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                              <DegradedBanner
                                feature="Sandbox validation report"
                                reasons={['No validation data available for this module.']}
                              />
                            )}
                          </AccordionSectionBody>
                        </Accordion.Item>

                        <Accordion.Item value="credentials" className="border-b border-zinc-800 last:border-b-0">
                          <AccordionSectionBody
                            icon={<KeyRound className="w-3.5 h-3.5" />}
                            label="Requested Credentials"
                          >
                          {review.credentials ? (
                            <div className="space-y-2 text-sm">
                              <div className="flex items-center gap-2">
                                {review.credentials.requires_api_key ? (
                                  <>
                                    <Lock className="w-4 h-4 text-yellow-400" />
                                    <span className="text-yellow-300">
                                      Requires {review.credentials.auth_type || 'API key'}
                                    </span>
                                  </>
                                ) : (
                                  <>
                                    <Unlock className="w-4 h-4 text-green-400" />
                                    <span className="text-green-300">
                                      No credentials required
                                    </span>
                                  </>
                                )}
                              </div>
                              {review.credentials.api_key_instructions && (
                                <p className="text-xs text-zinc-400">
                                  {review.credentials.api_key_instructions}
                                </p>
                              )}
                              {(review.blueprint?.credential_names ?? []).length > 0 && (
                                <div className="space-y-1">
                                  {review.blueprint.credential_names.map((name) => (
                                    <div
                                      key={name}
                                      className="text-xs text-zinc-300 px-2 py-1 rounded bg-zinc-800/60 font-mono"
                                    >
                                      {name}
                                    </div>
                                  ))}
                                </div>
                              )}
                            </div>
                          ) : (
                              <DegradedBanner
                                feature="Credential requirements"
                                reasons={['No credential data available for this module.']}
                              />
                            )}
                          </AccordionSectionBody>
                        </Accordion.Item>

                        <Accordion.Item value="repair-history" className="border-b border-zinc-800 last:border-b-0">
                          <AccordionSectionBody
                            icon={<History className="w-3.5 h-3.5" />}
                            label="Repair History"
                          >
                          {audit.length > 0 ? (
                            <div className="space-y-0">
                              {audit.map((attempt, i) => {
                                const colors =
                                  STAGE_COLORS[stageColorKey(attempt.stage)] ??
                                  STAGE_COLORS.scaffold;
                                return (
                                  <div key={attempt.attempt_number} className="flex gap-2">
                                    <div className="flex flex-col items-center">
                                      <div className="w-5 h-5 rounded-full bg-zinc-800 flex items-center justify-center text-[10px] text-zinc-300 flex-shrink-0">
                                        {attempt.attempt_number}
                                      </div>
                                      {i < audit.length - 1 && (
                                        <div className="w-px flex-1 border-l border-zinc-700 mt-1" />
                                      )}
                                    </div>
                                    <div className="flex-1 min-w-0 pb-3">
                                      <div className="flex items-center gap-1.5">
                                        <span
                                          className={`text-xs font-semibold uppercase ${colors.text}`}
                                        >
                                          {attempt.stage}
                                        </span>
                                        {attempt.status === 'success' ? (
                                          <CheckCircle2 className="w-3.5 h-3.5 text-green-400" />
                                        ) : attempt.status === 'failed' ? (
                                          <XCircle className="w-3.5 h-3.5 text-red-400" />
                                        ) : (
                                          <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin" />
                                        )}
                                      </div>
                                      {attempt.failure_fingerprint && (
                                        <div className="text-[10px] font-mono text-zinc-500 mt-0.5">
                                          {attempt.failure_fingerprint.slice(0, 8)}
                                        </div>
                                      )}
                                    </div>
                                  </div>
                                );
                              })}
                            </div>
                          ) : (
                            <p className="text-xs text-zinc-500">No repair attempts recorded.</p>
                          )}
                          </AccordionSectionBody>
                        </Accordion.Item>
                      </Accordion.Root>
                    </>
                  )}
                </>
              )}
            </div>

            {/* Sticky approve/reject footer (D-09) — below the scroll area */}
            {showReviewSurface &&
              (reviewState === 'open' || reviewState === 'approving' || reviewState === 'rejecting') && (
                <div className="border-t border-zinc-700 px-4 py-3 flex-shrink-0 space-y-2">
                  <textarea
                    value={rejectFeedback}
                    onChange={(e) => setRejectFeedback(e.target.value)}
                    disabled={busy}
                    rows={2}
                    placeholder="Optional: describe what to change…"
                    className="w-full text-sm bg-zinc-950 border border-zinc-700 rounded-md p-2 text-zinc-200 placeholder:text-zinc-600 resize-none disabled:opacity-50"
                  />

                  {rejectFeedback.trim() ? (
                    <p className="text-[11px] text-zinc-400">
                      This module will be sent back for one repair attempt using your
                      feedback. It will return here for another review — this is not final.
                    </p>
                  ) : confirmingReject ? (
                    <p className="text-[11px] text-red-400">
                      This permanently deletes the generated code, artifact bundle, and
                      version history for this module. This cannot be undone. Add feedback
                      instead to request a repair, or confirm to reject permanently.
                    </p>
                  ) : null}

                  <div className="flex gap-2">
                    <button
                      onClick={() => onApprove?.()}
                      disabled={busy}
                      className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium bg-green-500 hover:bg-green-600 disabled:bg-zinc-700 disabled:text-zinc-500 text-white transition-colors"
                    >
                      {reviewState === 'approving' ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <Check className="w-4 h-4" />
                      )}
                      Approve Module
                    </button>
                    <button
                      onClick={handleRejectClick}
                      disabled={busy}
                      className="flex-1 flex items-center justify-center gap-2 px-3 py-2 rounded-md text-sm font-medium bg-red-500 hover:bg-red-600 disabled:bg-zinc-700 disabled:text-zinc-500 text-white transition-colors"
                    >
                      {reviewState === 'rejecting' ? (
                        <Loader2 className="w-4 h-4 animate-spin" />
                      ) : (
                        <X className="w-4 h-4" />
                      )}
                      {rejectLabel}
                    </button>
                  </div>
                </div>
              )}
          </motion.div>
        </>
      )}
    </AnimatePresence>
  );
}
