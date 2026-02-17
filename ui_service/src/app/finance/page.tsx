/**
 * Finance Page (Native Next.js - No Iframe)
 *
 * XState-driven finance dashboard with Framer Motion transitions.
 * States:
 *   - locked: Credential form with connection testing
 *   - unlocked.loading: Loading indicator
 *   - unlocked.loaded: Full dashboard with charts and table
 *   - unlocked.error: Error state with retry
 *
 * Data flows through /api/dashboard/finance proxy route.
 * Lock status determined by XState root envelope via useNexusApp().
 */

'use client';

import React, { useState } from 'react';
import { useMachine } from '@xstate/react';
import { motion, AnimatePresence } from 'framer-motion';
import {
  DollarSign,
  Lock,
  Unlock,
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

  const [formData, setFormData] = useState({
    csv_path: '',
    api_key: '',
    api_url: '',
  });

  const handleSubmitCredentials = (e: React.FormEvent) => {
    e.preventDefault();
    send({ type: 'SUBMIT_CREDENTIALS', credentials: formData });
  };

  const handleRefresh = () => {
    send({ type: 'REFRESH' });
  };

  const handleRetry = () => {
    send({ type: 'RETRY' });
  };

  const handleDismiss = () => {
    send({ type: 'DISMISS' });
  };

  // ── Locked State (Connection Form) ────────────────────────────────────────

  const renderLocked = () => (
    <motion.div
      key="locked"
      variants={pageVariants}
      initial="initial"
      animate="animate"
      exit="exit"
      className="flex flex-col items-center justify-center h-full p-6"
    >
      <div className="max-w-md w-full space-y-6">
        {/* Lock Icon */}
        <div className="flex justify-center">
          <div className="rounded-full bg-yellow-500/10 p-6">
            <Lock className="w-12 h-12 text-yellow-500" />
          </div>
        </div>

        {/* Heading */}
        <div className="text-center space-y-2">
          <h1 className="text-2xl font-semibold">Connect Your Finance Source</h1>
          <p className="text-sm text-muted-foreground">
            Configure your finance data source to unlock detailed analytics and visualizations.
          </p>
        </div>

        {/* Connection Form */}
        <form onSubmit={handleSubmitCredentials} className="space-y-4">
          <div>
            <label
              htmlFor="csv_path"
              className="block text-sm font-medium mb-1.5"
            >
              CSV File Path
            </label>
            <input
              id="csv_path"
              type="text"
              value={formData.csv_path}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, csv_path: e.target.value }))
              }
              placeholder="/path/to/cibc-export.csv"
              className="w-full px-3 py-2 rounded-md border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div className="text-center text-sm text-muted-foreground">— OR —</div>

          <div>
            <label htmlFor="api_key" className="block text-sm font-medium mb-1.5">
              API Key
            </label>
            <input
              id="api_key"
              type="password"
              value={formData.api_key}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, api_key: e.target.value }))
              }
              placeholder="your-api-key"
              className="w-full px-3 py-2 rounded-md border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          <div>
            <label htmlFor="api_url" className="block text-sm font-medium mb-1.5">
              API URL
            </label>
            <input
              id="api_url"
              type="text"
              value={formData.api_url}
              onChange={(e) =>
                setFormData((prev) => ({ ...prev, api_url: e.target.value }))
              }
              placeholder="https://api.yourbank.com"
              className="w-full px-3 py-2 rounded-md border border-border bg-card text-foreground placeholder:text-muted-foreground focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>

          {/* Error Display */}
          {state.matches({ locked: 'failed' }) && state.context.error && (
            <motion.div
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="p-3 rounded-md bg-red-500/10 border border-red-500/20 text-red-500 text-sm flex items-start gap-2"
            >
              <AlertCircle className="w-4 h-4 mt-0.5 flex-shrink-0" />
              <div>
                <div className="font-medium">Connection Failed</div>
                <div className="opacity-90">{state.context.error}</div>
              </div>
            </motion.div>
          )}

          {/* Submit Button */}
          <button
            type="submit"
            disabled={state.matches({ locked: 'testing' })}
            className="w-full px-4 py-2 rounded-md bg-primary text-primary-foreground font-medium hover:bg-primary/90 disabled:opacity-50 disabled:cursor-not-allowed transition-colors flex items-center justify-center gap-2"
          >
            {state.matches({ locked: 'testing' }) ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Testing Connection...
              </>
            ) : (
              'Connect'
            )}
          </button>

          {state.matches({ locked: 'failed' }) && (
            <button
              type="button"
              onClick={handleDismiss}
              className="w-full px-4 py-2 rounded-md border border-border hover:bg-muted transition-colors text-sm"
            >
              Dismiss
            </button>
          )}
        </form>

        {/* Footer Note */}
        <p className="text-xs text-center text-muted-foreground">
          Supports CIBC CSV exports and compatible finance APIs
        </p>
      </div>
    </motion.div>
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
          <button
            onClick={handleRefresh}
            className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
            title="Refresh"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

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
      </motion.div>
    );
  };

  // ── Render Based on State ──────────────────────────────────────────────────

  return (
    <div className="h-full">
      <AnimatePresence mode="wait">
        {state.matches('locked') && renderLocked()}
        {state.matches({ unlocked: 'loading' }) && renderLoading()}
        {state.matches({ unlocked: 'error' }) && renderError()}
        {state.matches({ unlocked: 'loaded' }) && renderLoaded()}
      </AnimatePresence>
    </div>
  );
}
