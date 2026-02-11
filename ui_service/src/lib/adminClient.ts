/**
 * Admin API Client
 *
 * Typed fetch wrappers for the orchestrator admin API (port 8003)
 * and dashboard SSE stream (port 8001).
 */

const ADMIN_BASE =
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8003`
    : 'http://localhost:8003';

const DASHBOARD_BASE =
  typeof window !== 'undefined'
    ? `${window.location.protocol}//${window.location.hostname}:8001`
    : 'http://localhost:8001';

// ── Types ────────────────────────────────────────────────────────────────────

export interface ServiceState {
  name: string;
  state: 'running' | 'error' | 'idle';
  latency_ms: number;
  status_code?: number;
}

export interface ModuleState {
  id: string;
  name: string;
  state: 'running' | 'disabled' | 'failed';
  category?: string;
}

export interface PipelineState {
  services: Record<string, ServiceState>;
  modules: ModuleState[];
  adapters_count: number;
  timestamp: number;
  error?: string;
}

export interface ModuleDetail {
  module_id: string;
  name: string;
  category: string;
  platform: string;
  is_loaded: boolean;
  has_credentials: boolean;
  persistent_status?: string;
  failure_count?: number;
  success_count?: number;
  last_used?: string;
}

export interface ModuleActionResult {
  success: boolean;
  module_id: string;
  message: string;
}

export interface SystemInfo {
  routing: {
    categories: Record<string, unknown>;
    tiers: Record<string, unknown>;
    performance: Record<string, unknown>;
  };
  modules: { total: number; loaded: number };
  adapters: { count: number };
}

// ── Fetch helpers ────────────────────────────────────────────────────────────

async function adminFetch<T>(path: string, opts?: RequestInit): Promise<T> {
  const res = await fetch(`${ADMIN_BASE}${path}`, {
    ...opts,
    headers: { 'Content-Type': 'application/json', ...opts?.headers },
  });
  if (!res.ok) {
    const body = await res.text().catch(() => '');
    throw new Error(`Admin API ${res.status}: ${body}`);
  }
  return res.json();
}

// ── Admin API calls ──────────────────────────────────────────────────────────

export const adminApi = {
  health: () => adminFetch<{ status: string; modules_loaded: number }>('/admin/health'),

  // Modules
  listModules: () =>
    adminFetch<{ modules: ModuleDetail[]; total: number; loaded: number }>('/admin/modules'),

  getModule: (category: string, platform: string) =>
    adminFetch<ModuleDetail>(`/admin/modules/${category}/${platform}`),

  enableModule: (category: string, platform: string) =>
    adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}/enable`, { method: 'POST' }),

  disableModule: (category: string, platform: string) =>
    adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}/disable`, { method: 'POST' }),

  reloadModule: (category: string, platform: string) =>
    adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}/reload`, { method: 'POST' }),

  uninstallModule: (category: string, platform: string) =>
    adminFetch<ModuleActionResult>(`/admin/modules/${category}/${platform}`, { method: 'DELETE' }),

  // Routing config
  getRoutingConfig: () => adminFetch<Record<string, unknown>>('/admin/routing-config'),
  reloadConfig: () => adminFetch<{ status: string }>('/admin/routing-config/reload', { method: 'POST' }),

  // System
  systemInfo: () => adminFetch<SystemInfo>('/admin/system-info'),
};

// ── SSE stream ───────────────────────────────────────────────────────────────

export function connectPipelineSSE(
  onState: (state: PipelineState) => void,
  onError?: (err: Event) => void,
): EventSource {
  const es = new EventSource(`${DASHBOARD_BASE}/stream/pipeline-state`);
  es.onmessage = (e) => {
    try {
      onState(JSON.parse(e.data));
    } catch { /* ignore parse errors */ }
  };
  es.onerror = (e) => onError?.(e);
  return es;
}
