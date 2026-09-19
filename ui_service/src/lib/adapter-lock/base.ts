/**
 * Adapter lock/unlock base class architecture
 *
 * Mirrors the provider-lock pattern from Phase 4 for adapter connections.
 * Subclasses implement adapter-specific credential checking and connection testing.
 *
 * Reads: the orchestrator admin API module registry (GET /admin/modules) reports
 * `has_credentials` per module_id — credential values are never readable.
 * Writes: the dashboard credential store (POST/DELETE
 * /admin/module-credentials/{category}/{platform}) is the single write path.
 * Both services accept the same X-API-Key.
 */

const ADMIN_API_BASE = process.env.ADMIN_API_URL || 'http://orchestrator:8003';
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || process.env.X_API_KEY || '';
export const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard:8001';

export interface FieldDefinition {
  name: string;
  label: string;
  type: 'text' | 'password' | 'file';
  required: boolean;
}

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  latencyMs?: number;
  details?: Record<string, unknown>;
}

export interface AdapterLockStatus {
  locked: boolean;
  missingFields: string[];
  canTest: boolean;
}

export interface CredentialConfig {
  [key: string]: string | undefined;
}

/**
 * One GET /admin/modules per call: the set of module_ids ("category/platform")
 * that have stored credentials. Empty when the admin API is unreachable or
 * rejects the key, so every credentialed adapter then reports as locked.
 */
export async function fetchCredentialedModuleIds(): Promise<Set<string>> {
  const ids = new Set<string>();
  try {
    const res = await fetch(`${ADMIN_API_BASE}/admin/modules`, {
      headers: { 'Content-Type': 'application/json', 'X-API-Key': ADMIN_API_KEY },
      signal: AbortSignal.timeout(5000),
      cache: 'no-store',
    });
    if (!res.ok) return ids;
    const data = await res.json();
    for (const m of data?.modules || []) {
      if (m?.module_id && m.has_credentials) ids.add(m.module_id);
    }
  } catch {
    // Admin API unreachable — treat every credentialed adapter as locked
  }
  return ids;
}

/**
 * Base class for adapter unlock logic.
 * Each adapter subclass defines its required credential fields and connection test.
 */
export abstract class AdapterUnlockBase {
  constructor(
    protected adapterName: string,
    protected moduleId: string
  ) {}

  /**
   * Get field definitions required for this adapter.
   */
  abstract getRequiredFields(): FieldDefinition[];

  /**
   * Determine which required fields are missing from current credentials.
   */
  getMissingFields(credentials: CredentialConfig): string[] {
    return this.getRequiredFields()
      .filter((f) => f.required && !credentials[f.name])
      .map((f) => f.name);
  }

  /**
   * Determine if adapter is locked based on missing credentials.
   */
  isLocked(credentials: CredentialConfig): boolean {
    return this.getMissingFields(credentials).length > 0;
  }

  /**
   * Test connection to the adapter's external service.
   */
  abstract testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult>;

  /**
   * Get complete adapter lock status metadata.
   */
  toStatus(credentials: CredentialConfig): AdapterLockStatus {
    const missingFields = this.getMissingFields(credentials);
    return {
      locked: missingFields.length > 0,
      missingFields,
      canTest: missingFields.length === 0,
    };
  }

  /**
   * Dashboard credential-store path: moduleId "category/platform" split on the first "/".
   */
  private credentialPath(): string {
    const idx = this.moduleId.indexOf('/');
    const category = idx === -1 ? this.moduleId : this.moduleId.slice(0, idx);
    const platform = idx === -1 ? '' : this.moduleId.slice(idx + 1);
    return `${DASHBOARD_SERVICE}/admin/module-credentials/${encodeURIComponent(category)}/${encodeURIComponent(platform)}`;
  }

  /**
   * Store credentials in the dashboard credential store.
   * POST /admin/module-credentials/{category}/{platform}  body: { credentials }
   */
  async storeCredentials(credentials: Record<string, string>): Promise<boolean> {
    try {
      const res = await fetch(this.credentialPath(), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': ADMIN_API_KEY },
        body: JSON.stringify({ credentials }),
        signal: AbortSignal.timeout(5000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }

  /**
   * Remove credentials from the dashboard credential store.
   * DELETE /admin/module-credentials/{category}/{platform}
   */
  async deleteCredentials(): Promise<boolean> {
    try {
      const res = await fetch(this.credentialPath(), {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json', 'X-API-Key': ADMIN_API_KEY },
        signal: AbortSignal.timeout(5000),
      });
      return res.ok;
    } catch {
      return false;
    }
  }
}
