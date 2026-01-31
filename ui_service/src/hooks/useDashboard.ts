/**
 * Dashboard Hook
 * 
 * React hook for fetching and managing dashboard data.
 */
'use client';

import { useState, useEffect, useCallback } from 'react';
import { 
  DashboardContext, 
  AdaptersResponse, 
  FinanceContext, 
  CalendarContext, 
  HealthContext, 
  NavigationContext 
} from '@/types/dashboard';

interface UseDashboardOptions {
  refreshInterval?: number; // Auto-refresh interval in ms
  autoRefresh?: boolean;
}

interface UseDashboardReturn {
  // Data
  context: DashboardContext | null;
  adapters: AdaptersResponse | null;
  
  // Category shortcuts
  finance: FinanceContext | null;
  calendar: CalendarContext | null;
  health: HealthContext | null;
  navigation: NavigationContext | null;
  
  // State
  isLoading: boolean;
  error: string | null;
  lastUpdated: Date | null;
  
  // Actions
  refresh: () => Promise<void>;
  refreshCategory: (category: string) => Promise<void>;
  connectAdapter: (category: string, platform: string) => Promise<void>;
  disconnectAdapter: (category: string, platform: string) => Promise<void>;
}

export function useDashboard(options: UseDashboardOptions = {}): UseDashboardReturn {
  const { refreshInterval = 60000, autoRefresh = true } = options;
  
  const [context, setContext] = useState<DashboardContext | null>(null);
  const [adapters, setAdapters] = useState<AdaptersResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);
  
  // Fetch full context
  const refresh = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    
    try {
      const [contextRes, adaptersRes] = await Promise.all([
        fetch('/api/dashboard'),
        fetch('/api/dashboard/adapters'),
      ]);
      
      if (!contextRes.ok || !adaptersRes.ok) {
        throw new Error('Failed to fetch dashboard data');
      }
      
      const contextData = await contextRes.json();
      const adaptersData = await adaptersRes.json();
      
      setContext(contextData);
      setAdapters(adaptersData);
      setLastUpdated(new Date());
    } catch (err: any) {
      setError(err.message || 'Failed to load dashboard');
      console.error('[useDashboard] Error:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);
  
  // Refresh specific category
  const refreshCategory = useCallback(async (category: string) => {
    try {
      const res = await fetch(`/api/dashboard?category=${category}`);
      if (!res.ok) throw new Error(`Failed to fetch ${category}`);
      
      const data = await res.json();
      
      setContext(prev => {
        if (!prev) return prev;
        return {
          ...prev,
          context: {
            ...prev.context,
            [category]: data[category],
          },
          last_updated: {
            ...prev.last_updated,
            [category]: new Date().toISOString(),
          },
        };
      });
    } catch (err: any) {
      console.error(`[useDashboard] Error refreshing ${category}:`, err);
    }
  }, []);
  
  // Connect adapter
  const connectAdapter = useCallback(async (category: string, platform: string) => {
    try {
      const res = await fetch('/api/dashboard/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, platform, action: 'connect' }),
      });
      
      if (!res.ok) throw new Error('Failed to connect adapter');
      
      const data = await res.json();
      
      // If OAuth needed, redirect
      if (data.oauth_url) {
        window.location.href = data.oauth_url;
        return;
      }
      
      // Refresh adapters list
      const adaptersRes = await fetch('/api/dashboard/adapters');
      if (adaptersRes.ok) {
        setAdapters(await adaptersRes.json());
      }
    } catch (err: any) {
      console.error('[useDashboard] Connect error:', err);
      throw err;
    }
  }, []);
  
  // Disconnect adapter
  const disconnectAdapter = useCallback(async (category: string, platform: string) => {
    try {
      const res = await fetch('/api/dashboard/adapters', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, platform, action: 'disconnect' }),
      });
      
      if (!res.ok) throw new Error('Failed to disconnect adapter');
      
      // Refresh adapters list
      const adaptersRes = await fetch('/api/dashboard/adapters');
      if (adaptersRes.ok) {
        setAdapters(await adaptersRes.json());
      }
    } catch (err: any) {
      console.error('[useDashboard] Disconnect error:', err);
      throw err;
    }
  }, []);
  
  // Initial fetch
  useEffect(() => {
    refresh();
  }, [refresh]);
  
  // Auto-refresh
  useEffect(() => {
    if (!autoRefresh || refreshInterval <= 0) return;
    
    const interval = setInterval(refresh, refreshInterval);
    return () => clearInterval(interval);
  }, [refresh, autoRefresh, refreshInterval]);
  
  return {
    context,
    adapters,
    finance: context?.context.finance ?? null,
    calendar: context?.context.calendar ?? null,
    health: context?.context.health ?? null,
    navigation: context?.context.navigation ?? null,
    isLoading,
    error,
    lastUpdated,
    refresh,
    refreshCategory,
    connectAdapter,
    disconnectAdapter,
  };
}
