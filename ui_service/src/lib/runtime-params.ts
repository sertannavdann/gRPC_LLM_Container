export const CAPABILITY_POLL_INTERVAL_MS = 30_000;
export const CONFIG_POLL_INTERVAL_MS = 30_000;
export const CAPABILITY_RETRY_DELAY_MS = 5_000;

export const ADMIN_REQUEST_TIMEOUT_MS = 8_000;

export const ENABLE_READONLY_FALLBACK = true;

export const READONLY_FALLBACK_PATHS = [
  '/admin/capabilities',
  '/admin/feature-health',
  '/admin/config/version',
] as const;

export type FallbackReason = 'admin_auth_required' | 'upstream_unavailable';
export const FALLBACK_SOURCE = 'ui_admin_proxy';