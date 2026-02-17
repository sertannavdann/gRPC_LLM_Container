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

// ── Capability Contract Types (Phase 6) ─────────────────────────────────────

export enum FeatureStatus {
  HEALTHY = 'healthy',
  DEGRADED = 'degraded',
  UNAVAILABLE = 'unavailable',
  UNKNOWN = 'unknown',
}

export interface ToolCapability {
  name: string;
  description: string;
  registered: boolean;
  category: 'builtin' | 'custom';
}

export interface ModuleCapability {
  id: string;
  name: string;
  category: string;
  platform: string;
  status: 'installed' | 'draft' | 'disabled';
  version: number | null;
  has_tests: boolean;
}

export interface ProviderCapability {
  id: string;
  name: string;
  tier: 'standard' | 'heavy' | 'ultra';
  locked: boolean;
  connection_tested: boolean;
  last_test_ok: boolean | null;
}

export interface AdapterCapability {
  id: string;
  name: string;
  category: string;
  locked: boolean;
  missing_fields: string[];
  last_data_timestamp: string | null;
  connection_tested: boolean;
  last_test_ok: boolean | null;
}

export interface FeatureHealth {
  feature: string;
  status: FeatureStatus;
  degraded_reasons: string[];
  dependencies: string[];
}

export interface CapabilityEnvelope {
  tools: ToolCapability[];
  modules: ModuleCapability[];
  providers: ProviderCapability[];
  adapters: AdapterCapability[];
  features: FeatureHealth[];
  config_version: string;
  timestamp: string;
}

export interface CapabilityResponse {
  data: CapabilityEnvelope | null;
  etag: string;
  notModified: boolean;
}

export interface ConfigVersionResponse {
  config_version: string;
  etag: string;
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

  // Capability Contract (Phase 6)
  getCapabilities: async (etag?: string): Promise<CapabilityResponse> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (etag) {
      headers['If-None-Match'] = `"${etag}"`;
    }

    const res = await fetch(`${ADMIN_BASE}/admin/capabilities`, { headers });

    if (res.status === 304) {
      return { data: null, etag: etag!, notModified: true };
    }

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`Admin API ${res.status}: ${body}`);
    }

    const data = await res.json();
    const responseEtag = res.headers.get('ETag')?.replace(/"/g, '') || '';

    return { data, etag: responseEtag, notModified: false };
  },

  getFeatureHealth: () => adminFetch<FeatureHealth[]>('/admin/feature-health'),

  getConfigVersion: async (etag?: string): Promise<ConfigVersionResponse> => {
    const headers: Record<string, string> = { 'Content-Type': 'application/json' };
    if (etag) {
      headers['If-None-Match'] = `"${etag}"`;
    }

    const res = await fetch(`${ADMIN_BASE}/admin/config/version`, { headers });

    if (res.status === 304) {
      // On 304, return current etag (unchanged)
      return { config_version: '', etag: etag! };
    }

    if (!res.ok) {
      const body = await res.text().catch(() => '');
      throw new Error(`Admin API ${res.status}: ${body}`);
    }

    const data = await res.json();
    const responseEtag = res.headers.get('ETag')?.replace(/"/g, '') || '';

    return { config_version: data.config_version, etag: responseEtag };
  },
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
