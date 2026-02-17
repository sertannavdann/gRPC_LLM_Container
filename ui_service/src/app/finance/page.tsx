/**
 * Finance Page
 *
 * Shows finance adapter lock/unlock status with API proxy data preview.
 * No iframe — data flows through /api/finance proxy route.
 */
'use client';

import React, { useState, useEffect } from 'react';
import { DollarSign, Lock, Unlock, RefreshCw, AlertCircle } from 'lucide-react';

interface AdapterStatus {
  status: 'connected' | 'locked' | 'error' | 'loading';
  missingFields: string[];
}

interface BankSummary {
  total_transactions?: number;
  total_income?: number;
  total_expenses?: number;
  date_range?: { start: string; end: string };
}

export default function FinancePage() {
  const [adapterStatus, setAdapterStatus] = useState<AdapterStatus>({
    status: 'loading',
    missingFields: [],
  });
  const [summary, setSummary] = useState<BankSummary | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkStatus();
  }, []);

  async function checkStatus() {
    setLoading(true);
    try {
      const res = await fetch('/api/adapters');
      if (res.ok) {
        const data = await res.json();
        const finance = data.adapters?.find(
          (a: any) => a.category === 'finance'
        );
        if (finance) {
          setAdapterStatus({
            status: finance.status,
            missingFields: finance.missingFields || [],
          });

          // If connected, fetch summary preview
          if (finance.status === 'connected') {
            await fetchSummary();
          }
        } else {
          setAdapterStatus({ status: 'error', missingFields: [] });
        }
      }
    } catch {
      setAdapterStatus({ status: 'error', missingFields: [] });
    } finally {
      setLoading(false);
    }
  }

  async function fetchSummary() {
    try {
      const dashboardUrl =
        typeof window !== 'undefined'
          ? `${window.location.protocol}//${window.location.hostname}:8001`
          : 'http://localhost:8001';
      const res = await fetch(`${dashboardUrl}/bank/summary`, {
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        setSummary(data);
      }
    } catch {
      // Summary not available — non-critical
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-pulse text-muted-foreground">
          Loading finance adapter status...
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full p-6 space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <DollarSign className="w-6 h-6 text-green-500" />
          <h1 className="text-xl font-semibold">Finance Dashboard</h1>
        </div>
        <button
          onClick={checkStatus}
          className="p-2 rounded-md text-muted-foreground hover:text-foreground hover:bg-muted transition-colors"
          title="Refresh"
        >
          <RefreshCw className="w-4 h-4" />
        </button>
      </div>

      {/* Status Card */}
      <div className="rounded-lg border border-border bg-card p-6">
        {adapterStatus.status === 'locked' && (
          <div className="flex items-start gap-4">
            <Lock className="w-8 h-8 text-yellow-500 mt-1" />
            <div>
              <h2 className="text-lg font-medium">Finance Adapter Locked</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Configure your finance data source to unlock this page.
              </p>
              {adapterStatus.missingFields.length > 0 && (
                <div className="mt-3">
                  <p className="text-sm font-medium">Missing credentials:</p>
                  <ul className="list-disc list-inside text-sm text-muted-foreground mt-1">
                    {adapterStatus.missingFields.map((field) => (
                      <li key={field}>{field}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="text-xs text-muted-foreground mt-4">
                Use the Settings &gt; Adapters page to configure credentials.
              </p>
            </div>
          </div>
        )}

        {adapterStatus.status === 'connected' && (
          <div className="flex items-start gap-4">
            <Unlock className="w-8 h-8 text-green-500 mt-1" />
            <div className="flex-1">
              <h2 className="text-lg font-medium">Finance Data Connected</h2>
              <p className="text-sm text-muted-foreground mt-1">
                CIBC CSV adapter is active. Full visualization coming in Phase 6.
              </p>

              {/* Summary Preview */}
              {summary && (
                <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                  {summary.total_transactions != null && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">Transactions</div>
                      <div className="text-lg font-semibold">
                        {summary.total_transactions.toLocaleString()}
                      </div>
                    </div>
                  )}
                  {summary.total_income != null && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">Income</div>
                      <div className="text-lg font-semibold text-green-500">
                        ${summary.total_income.toLocaleString()}
                      </div>
                    </div>
                  )}
                  {summary.total_expenses != null && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">Expenses</div>
                      <div className="text-lg font-semibold text-red-500">
                        ${Math.abs(summary.total_expenses).toLocaleString()}
                      </div>
                    </div>
                  )}
                  {summary.date_range && (
                    <div className="rounded-md bg-muted/50 p-3">
                      <div className="text-xs text-muted-foreground">Period</div>
                      <div className="text-sm font-medium">
                        {summary.date_range.start} — {summary.date_range.end}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </div>
        )}

        {adapterStatus.status === 'error' && (
          <div className="flex items-start gap-4">
            <AlertCircle className="w-8 h-8 text-red-500 mt-1" />
            <div>
              <h2 className="text-lg font-medium">Finance Adapter Unavailable</h2>
              <p className="text-sm text-muted-foreground mt-1">
                Could not connect to the adapter registry. Ensure the Admin API is running.
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
