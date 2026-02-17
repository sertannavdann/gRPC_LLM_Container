/**
 * Adapter lock/unlock base class architecture
 *
 * Mirrors the provider-lock pattern from Phase 4 for adapter connections.
 * Subclasses implement adapter-specific credential checking and connection testing.
 * Credentials flow through Admin API, not .env files.
 */

const ADMIN_API_BASE = process.env.ADMIN_API_URL || 'http://localhost:8003';

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
 * Base class for adapter unlock logic.
 * Each adapter subclass defines its required credential fields and connection test.
 * Credentials are read from Admin API module registry, not from .env or hardcoded values.
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
   * Fetch current credentials from Admin API module registry.
   */
  async fetchCredentials(): Promise<CredentialConfig> {
    try {
      const res = await fetch(
        `${ADMIN_API_BASE}/admin/modules/${encodeURIComponent(this.moduleId)}/credentials`,
        { headers: { 'Content-Type': 'application/json' } }
      );
      if (!res.ok) return {};
      const data = await res.json();
      return data.credentials || data || {};
    } catch {
      return {};
    }
  }

  /**
   * Store credentials via Admin API.
   */
  async storeCredentials(credentials: Record<string, string>): Promise<boolean> {
    try {
      const res = await fetch(
        `${ADMIN_API_BASE}/admin/modules/${encodeURIComponent(this.moduleId)}/credentials`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ credentials }),
        }
      );
      return res.ok;
    } catch {
      return false;
    }
  }
}
