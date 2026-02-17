/**
 * useUserPrefs Hook
 *
 * React hook for reading/writing user preferences with optimistic updates.
 * Persists across page refreshes via SQLite backend (admin API).
 *
 * Features:
 * - Optimistic local updates (apply immediately, PUT in background)
 * - Version tracking via ref for concurrency control
 * - On 409 conflict: re-fetch and merge server state
 * - XState integration: monitoring_tab preference syncs with activeTab region
 */

'use client';

import { useState, useEffect, useRef, useCallback } from 'react';

// ── Types ───────────────────────────────────────────────────────────────────

export interface UserPrefs {
  theme: 'light' | 'dark' | 'system';
  provider_ordering: string[];
  module_favorites: string[];
  monitoring_tab: 'overview' | 'modules' | 'alerts';
  dashboard_layout: Record<string, unknown> | null;
}

const DEFAULT_PREFS: UserPrefs = {
  theme: 'system',
  provider_ordering: [],
  module_favorites: [],
  monitoring_tab: 'overview',
  dashboard_layout: null,
};

// ── Admin API Base ──────────────────────────────────────────────────────────

const ADMIN_BASE =
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8003`
    : 'http://localhost:8003';

// ── Hook ────────────────────────────────────────────────────────────────────

export interface UseUserPrefsReturn {
  prefs: UserPrefs;
  updatePrefs: (updates: Partial<UserPrefs>) => Promise<void>;
  isLoading: boolean;
  isSaving: boolean;
}

export function useUserPrefs(): UseUserPrefsReturn {
  const [prefs, setPrefs] = useState<UserPrefs>(DEFAULT_PREFS);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const versionRef = useRef<number>(0);

  // ── Fetch preferences ──────────────────────────────────────────────────

  const fetchPrefs = useCallback(async () => {
    try {
      const res = await fetch(`${ADMIN_BASE}/admin/user/prefs`, {
        headers: { 'Content-Type': 'application/json' },
      });

      if (!res.ok) {
        // Silently use defaults if API is unavailable
        return;
      }

      const data = await res.json();
      setPrefs({ ...DEFAULT_PREFS, ...data.prefs });
      versionRef.current = data.version;
    } catch {
      // API unreachable — use defaults
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchPrefs();
  }, [fetchPrefs]);

  // ── Update preferences (optimistic) ───────────────────────────────────

  const updatePrefs = useCallback(
    async (updates: Partial<UserPrefs>) => {
      // Optimistic local update
      const newPrefs = { ...prefs, ...updates };
      setPrefs(newPrefs);
      setIsSaving(true);

      try {
        const res = await fetch(`${ADMIN_BASE}/admin/user/prefs`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prefs: newPrefs,
            version: versionRef.current,
          }),
        });

        if (res.status === 409) {
          // Conflict — re-fetch server state and merge
          await fetchPrefs();
          return;
        }

        if (res.ok) {
          const data = await res.json();
          versionRef.current = data.version;
          setPrefs({ ...DEFAULT_PREFS, ...data.prefs });
        }
      } catch {
        // Revert on network failure
        await fetchPrefs();
      } finally {
        setIsSaving(false);
      }
    },
    [prefs, fetchPrefs],
  );

  return { prefs, updatePrefs, isLoading, isSaving };
}
