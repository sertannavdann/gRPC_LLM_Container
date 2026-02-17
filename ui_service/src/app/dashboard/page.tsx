/**
 * Dashboard Page - Capability-Driven Adapter Management
 *
 * Displays adapter cards driven by XState capability envelope.
 * Uses Framer Motion for animated grid transitions.
 * Connects/disconnects adapters through Admin API (not .env manipulation).
 */
'use client';

import React, { useState } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { Loader2, AlertCircle, RefreshCw, Activity, CheckCircle } from 'lucide-react';
import { useNexusApp } from '@/hooks/useNexusApp';
import { AdapterCard } from '@/components/dashboard/AdapterCard';
import { DataSourceIndicator } from '@/components/dashboard/DataSourceIndicator';
import type { AdapterCapability, FeatureStatus } from '@/lib/adminClient';

export default function DashboardPage() {
  const { envelope, isLoading, isError, error, isLive, isMock, isOffline, isUnknown, refresh } =
    useNexusApp();

  const [isRefreshing, setIsRefreshing] = useState(false);

  /**
   * Determine data source status for indicator
   */
  const getDataSourceStatus = (): 'live' | 'mock' | 'offline' | 'unknown' => {
    if (isLive) return 'live';
    if (isMock) return 'mock';
    if (isOffline) return 'offline';
    return 'unknown';
  };

  /**
   * Handle manual refresh
   */
  const handleRefresh = async () => {
    setIsRefreshing(true);
    await refresh();
    setTimeout(() => setIsRefreshing(false), 500);
  };

  /**
   * Connect adapter: store credentials and test connection
   */
  const handleConnect = async (adapter: AdapterCapability) => {
    // For locked adapters, we need credentials
    // In a real implementation, this would show a modal to collect credentials
    // For now, we'll show an alert
    if (adapter.missing_fields.length > 0) {
      alert(
        `This adapter requires configuration: ${adapter.missing_fields.join(', ')}. Please configure it in the Settings page.`
      );
      return;
    }

    try {
      const response = await fetch('/api/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adapterId: adapter.id,
          credentials: {}, // Credentials should be collected from a modal
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to connect adapter: ${response.statusText}`);
      }

      const result = await response.json();

      // Refresh capability envelope to reflect new status
      await refresh();

      if (result.connectionTest?.success) {
        // Success feedback is handled by the adapter card status update
      } else {
        throw new Error(result.connectionTest?.message || 'Connection test failed');
      }
    } catch (err: any) {
      throw new Error(err.message || 'Failed to connect adapter');
    }
  };

  /**
   * Disconnect adapter: remove credentials
   */
  const handleDisconnect = async (adapter: AdapterCapability) => {
    try {
      const response = await fetch('/api/adapters', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          adapterId: adapter.id,
        }),
      });

      if (!response.ok) {
        throw new Error(`Failed to disconnect adapter: ${response.statusText}`);
      }

      // Refresh capability envelope to reflect new status
      await refresh();
    } catch (err: any) {
      throw new Error(err.message || 'Failed to disconnect adapter');
    }
  };

  /**
   * Get feature health status summary
   */
  const getFeatureHealthSummary = () => {
    if (!envelope?.features) return null;

    const counts = envelope.features.reduce(
      (acc, f) => {
        acc[f.status] = (acc[f.status] || 0) + 1;
        return acc;
      },
      {} as Record<string, number>
    );

    return counts;
  };

  /**
   * Render feature health bar
   */
  const FeatureHealthBar = () => {
    const healthSummary = getFeatureHealthSummary();
    if (!healthSummary) return null;

    const total = Object.values(healthSummary).reduce((a, b) => a + b, 0);
    if (total === 0) return null;

    return (
      <div className="flex items-center gap-3 px-4 py-3 bg-gray-800/50 rounded-lg border border-gray-700">
        <Activity className="w-4 h-4 text-gray-400" />
        <span className="text-sm font-medium text-gray-300">System Health:</span>
        <div className="flex-1 flex items-center gap-2">
          {healthSummary['healthy'] && (
            <div className="flex items-center gap-1 text-xs text-green-400">
              <div className="w-2 h-2 rounded-full bg-green-400" />
              {healthSummary['healthy']} healthy
            </div>
          )}
          {healthSummary['degraded'] && (
            <div className="flex items-center gap-1 text-xs text-amber-400">
              <div className="w-2 h-2 rounded-full bg-amber-400" />
              {healthSummary['degraded']} degraded
            </div>
          )}
          {healthSummary['unavailable'] && (
            <div className="flex items-center gap-1 text-xs text-red-400">
              <div className="w-2 h-2 rounded-full bg-red-400" />
              {healthSummary['unavailable']} unavailable
            </div>
          )}
        </div>
      </div>
    );
  };

  /**
   * Loading state with skeleton cards
   */
  if (isLoading && !envelope) {
    return (
      <div className="h-full flex flex-col bg-background">
        {/* Header Skeleton */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-border">
          <div className="flex items-center gap-4">
            <div className="h-6 w-48 bg-muted animate-pulse rounded" />
            <div className="h-6 w-20 bg-muted animate-pulse rounded-full" />
          </div>
          <div className="h-8 w-8 bg-muted animate-pulse rounded-lg" />
        </div>

        {/* Skeleton Cards */}
        <div className="flex-1 overflow-auto p-6">
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
            {[1, 2, 3, 4, 5, 6, 7, 8].map((i) => (
              <div key={i} className="h-48 bg-muted animate-pulse rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    );
  }

  /**
   * Error state
   */
  if (isError && !envelope) {
    return (
      <div className="h-full flex flex-col items-center justify-center bg-background">
        <AlertCircle className="w-12 h-12 text-destructive mb-4" />
        <h2 className="text-xl font-semibold mb-2">Failed to load dashboard</h2>
        <p className="text-muted-foreground mb-6 max-w-md text-center">
          {error?.message || 'Unable to fetch capability data from the backend'}
        </p>
        <button
          onClick={handleRefresh}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors"
        >
          <RefreshCw className="w-4 h-4" />
          Try Again
        </button>
      </div>
    );
  }

  /**
   * Main dashboard view
   */
  return (
    <div className="h-full flex flex-col bg-background">
      {/* Header */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-border bg-card/50 backdrop-blur-sm">
        <div className="flex items-center gap-4">
          <h1 className="text-2xl font-bold">NEXUS Dashboard</h1>
          <DataSourceIndicator status={getDataSourceStatus()} />
        </div>

        <button
          onClick={handleRefresh}
          disabled={isRefreshing}
          className="p-2 text-muted-foreground hover:text-foreground hover:bg-muted rounded-lg transition-colors disabled:opacity-50"
          title="Refresh capability data"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {/* Feature Health Bar */}
      {envelope?.features && envelope.features.length > 0 && (
        <div className="px-6 pt-4">
          <FeatureHealthBar />
        </div>
      )}

      {/* Adapter Cards Grid */}
      <div className="flex-1 overflow-auto p-6">
        {!envelope?.adapters || envelope.adapters.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full text-muted-foreground">
            <CheckCircle className="w-12 h-12 mb-4" />
            <p>No adapters configured</p>
          </div>
        ) : (
          <AnimatePresence mode="popLayout">
            <motion.div
              layout
              className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4"
            >
              {envelope.adapters.map((adapter) => (
                <AdapterCard
                  key={adapter.id}
                  adapter={adapter}
                  onConnect={() => handleConnect(adapter)}
                  onDisconnect={() => handleDisconnect(adapter)}
                />
              ))}
            </motion.div>
          </AnimatePresence>
        )}
      </div>
    </div>
  );
}
