/**
 * Finance Page (Native Next.js - No Iframe)
 *
 * XState-driven finance dashboard with Framer Motion transitions.
 * States:
 *   - unlocked.loading: Loading indicator
 *   - unlocked.loaded: Full dashboard with charts and table, or an empty-state
 *     CSV drop zone when no transactions are loaded
 *   - unlocked.uploading: CSV upload in flight
 *   - unlocked.error: Error state with retry
 *
 * Data flows through /api/dashboard/finance proxy route. CSV exports are
 * uploaded through /api/dashboard/finance/upload (dashboard POST /bank/upload);
 * the CIBC adapter needs no credentials, so there is no locked state.
 */

'use client';

import React, { useRef, useState } from 'react';
import { useMachine } from '@xstate/react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DollarSign,
  Unlock,
  Upload,
  FileText,
  RefreshCw,
  AlertCircle,
  Loader2,
  TrendingUp,
  TrendingDown,
  Activity,
} from 'lucide-react';

import { financePageMachine } from '@/machines/financePage';
import { useNexusApp } from '@/hooks/useNexusApp';
import { TransactionTable } from '@/components/finance/TransactionTable';
import {
  SpendingChart,
  CategoryBreakdown,
  generateMockSpendingData,
  generateMockCategoryData,
} from '@/components/finance/SpendingChart';

// ── Framer Motion Variants ───────────────────────────────────────────────────

const pageVariants = {
  initial: { opacity: 0, y: 20 },
  animate: { opacity: 1, y: 0, transition: { duration: 0.3 } },
  exit: { opacity: 0, y: -20, transition: { duration: 0.2 } },
};

const skeletonVariants = {
  initial: { opacity: 0 },
  animate: { opacity: 1, transition: { duration: 0.2 } },
  exit: { opacity: 0, transition: { duration: 0.1 } },
};

// ── Main Component ───────────────────────────────────────────────────────────

export default function FinancePage() {
  const { envelope } = useNexusApp();
  const [state, send] = useMachine(financePageMachine, {
    input: { envelope },
  });

  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragActive, setDragActive] = useState(false);

  const isUploading = state.matches({ unlocked: 'uploading' });

  const handleRefresh = () => {
    send({ type: 'REFRESH' });
  };

  const handleRetry = () => {
    send({ type: 'RETRY' });
  };

  const handleFile = (file: File | null | undefined) => {
    if (file) send({ type: 'UPLOAD_CSV', file });
  };

  const openFilePicker = () => {
    fileInputRef.current?.click();
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    if (!dragActive) setDragActive(true);
  };

  const handleDragLeave = () => {
    setDragActive(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    handleFile(e.dataTransfer.files?.[0]);
  };

  // ── Upload Feedback (error + confirmation) ────────────────────────────────

  const renderUploadFeedback = () => (
    <>
      {state.context.uploadError && (
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          className="p-3 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-start gap-2"
        >
          <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
          <div>
            <div className="font-medium">Upload Failed</div>
            <div className="opacity-90">{state.context.uploadError}</div>
          </div>
        </motion.div>
      )}

      {state.context.lastUpload && (
        <div className="p-3 rounded-md bg-green-500/10 border border-green-500/20 text-green-500 text-sm flex items-center gap-2">
          <FileText className="w-4 h-4 flex-shrink-0" />
          <span>
            {state.context.lastUpload.transactions.toLocaleString()} transactions loaded from{' '}
            {state.context.lastUpload.file}
          </span>
        </div>
      )}
    </>
  );

  // ── Empty State (CSV Drop Zone) ───────────────────────────────────────────

  const renderEmptyDropZone = () => (
    <div
      role="button"
      tabIndex={0}
      onClick={openFilePicker}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          openFilePicker();
        }
      }}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className={`flex flex-col items-center justify-center gap-3 p-12 rounded-lg border-2 border-dashed cursor-pointer transition-colors ${
        dragActive
          ? 'border-primary bg-primary/5'
          : 'border-border bg-card hover:border-primary/50'
      }`}
    >
      <div className="rounded-full bg-primary/10 p-4">
        <Upload className="w-8 h-8 text-primary" />
      </div>
      <div className="text-center space-y-1">
        <div className="font-medium">No transactions yet</div>
        <p className="text-sm text-muted-foreground">
          Drop a CIBC CSV export here, or click to choose a file.
        </p>
      </div>
    </div>
  );

  // ── Loading State ──────────────────────────────────────────────────────────

  const renderLoading = () => (
    <motion.div
      key="loading"
      variants={skeletonVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex flex-col items-center justify-center h-full p-6"
    >
      <Loader2 className="w-12 h-12 text-primary animate-spin" />
      <p className="mt-4 text-muted-foreground">Loading financial data...</p>
    </motion.div>
  );

  // ── Uploading State ────────────────────────────────────────────────────────

  const renderUploading = () => (
    <motion.div
      key="uploading"
      variants={skeletonVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex flex-col items-center justify-center h-full p-6"
    >
      <Loader2 className="w-12 h-12 text-primary animate-spin" />
      <p className="mt-4 text-muted-foreground">
        Uploading {state.context.pendingFile?.name || 'CSV'}...
      </p>
    </motion.div>
  );

  // ── Error State ────────────────────────────────────────────────────────────

  const renderError = () => (
    <motion.div
      key="error"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex flex-col items-center justify-center h-full p-6"
    >
      <AlertCircle className="w-12 h-12 text-red-500 mb-4" />
      <h2 className="text-xl font-semibold mb-2">Failed to Load Data</h2>
      <p className="text-muted-foreground mb-6 text-center max-w-md">
        {state.context.error || 'An unexpected error occurred'}
      </p>
      <button
        onClick={handleRetry}
        className="px-4 py-2 rounded-md bg-primary text-primary-foreground hover:bg-primary/90 transition-colors"
      >
        Retry
      </button>
    </motion.div>
  );

  // ── Loaded State (Dashboard) ───────────────────────────────────────────────

  const renderLoaded = () => {
    const { transactions, summary } = state.context;
    const isEmpty = transactions.length === 0;

    // Generate chart data from transactions (last 6 months)
    const spendingData = generateMockSpendingData(); // TODO: Compute from transactions
    const categoryData = generateMockCategoryData(); // TODO: Compute from transactions

    return (
      <motion.div
        key="loaded"
        variants={pageVariants}
        initial="initial"
        animate="animate"
        exit="exit"
        className="flex flex-col h-full p-6 space-y-6 overflow-auto"
      >
        {/* Header */}
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <DollarSign className="w-6 h-6 text-green-500" />
            <h1 className="text-xl font-semibold">Finance Dashboard</h1>
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={openFilePicker}
              disabled={isUploading}
              className="flex items-center gap-2 px-3 py-1.5 rounded-md border border-border text-sm hover:bg-muted transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              title="Upload a CIBC CSV export"
            >
              <Upload className="w-4 h-4" />
              Upload CSV
            </button>
            <button
              onClick={handleRefresh}
              className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
              title="Refresh"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {renderUploadFeedback()}

        {isEmpty ? (
          renderEmptyDropZone()
        ) : (
          <>
            {/* Summary Cards */}
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <TrendingUp className="w-4 h-4" />
                  Total Income
                </div>
                <div className="text-2xl font-semibold text-green-500">
                  ${summary?.total_income_period.toLocaleString() || '0'}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <TrendingDown className="w-4 h-4" />
                  Total Expenses
                </div>
                <div className="text-2xl font-semibold text-red-500">
                  ${Math.abs(summary?.total_expenses_period || 0).toLocaleString()}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <Activity className="w-4 h-4" />
                  Net Balance
                </div>
                <div
                  className={`text-2xl font-semibold ${
                    (summary?.net_cashflow || 0) >= 0
                      ? 'text-green-500'
                      : 'text-red-500'
                  }`}
                >
                  ${Math.abs(summary?.net_cashflow || 0).toLocaleString()}
                </div>
              </div>

              <div className="rounded-lg border border-border bg-card p-4">
                <div className="flex items-center gap-2 text-sm text-muted-foreground mb-1">
                  <Unlock className="w-4 h-4" />
                  Transactions
                </div>
                <div className="text-2xl font-semibold">
                  {summary?.recent_count.toLocaleString() || '0'}
                </div>
              </div>
            </div>

            {/* Main Content: Transactions + Charts */}
            <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
              {/* Left Column: Transactions (2/3 width) */}
              <div className="lg:col-span-2 rounded-lg border border-border bg-card p-5">
                <h2 className="text-lg font-semibold mb-4">Recent Transactions</h2>
                <TransactionTable transactions={transactions} />
              </div>

              {/* Right Column: Charts (1/3 width) */}
              <div className="space-y-6">
                {/* Category Breakdown */}
                <div className="rounded-lg border border-border bg-card p-5">
                  <h2 className="text-lg font-semibold mb-4">Category Breakdown</h2>
                  <CategoryBreakdown data={categoryData} />
                </div>

                {/* Spending Trend */}
                <div className="rounded-lg border border-border bg-card p-5">
                  <h2 className="text-lg font-semibold mb-4">Spending Trend</h2>
                  <SpendingChart data={spendingData} />
                </div>
              </div>
            </div>
          </>
        )}
      </motion.div>
    );
  };

  // ── Render Based on State ──────────────────────────────────────────────────

  return (
    <div className="h-full">
      {/* Hidden file input shared by the header button and the drop zone */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => {
          handleFile(e.target.files?.[0]);
          e.target.value = '';
        }}
      />
      <AnimatePresence mode="wait">
        {state.matches({ unlocked: 'loading' }) && renderLoading()}
        {state.matches({ unlocked: 'uploading' }) && renderUploading()}
        {state.matches({ unlocked: 'error' }) && renderError()}
        {state.matches({ unlocked: 'loaded' }) && renderLoaded()}
      </AnimatePresence>
    </div>
  );
}
