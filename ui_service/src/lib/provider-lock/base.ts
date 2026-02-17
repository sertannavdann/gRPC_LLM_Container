/**
 * Provider lock/unlock base class architecture
 *
 * Defines reusable contract for provider requirement checking and connection testing.
 * Subclasses implement provider-specific validation logic.
 */

export interface ConnectionTestResult {
  success: boolean;
  message: string;
  details?: Record<string, unknown>;
}

export interface ProviderLockStatus {
  locked: boolean;
  missingRequirements: string[];
  canTest: boolean;
}

export interface EnvConfig {
  [key: string]: string | undefined;
}

/**
 * Base class for provider unlock logic.
 * Each provider subclass defines its required fields and connection test implementation.
 */
export abstract class ProviderUnlockBase {
  constructor(protected providerName: string) {}

  /**
   * Get list of required environment variable names for this provider.
   * @param envConfig - Current environment configuration
   * @returns Array of missing required field names
   */
  abstract getRequiredFields(envConfig: EnvConfig): string[];

  /**
   * Determine if provider is locked based on missing requirements.
   * @param envConfig - Current environment configuration
   * @returns true if provider lacks required connection prerequisites
   */
  isLocked(envConfig: EnvConfig): boolean {
    return this.getRequiredFields(envConfig).length > 0;
  }

  /**
   * Test connection to provider API/service.
   * @param payload - Test parameters (may include temporary key overrides)
   * @returns Structured test result with success status and message
   */
  abstract testConnection(payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult>;

  /**
   * Get complete provider lock status metadata.
   * @param envConfig - Current environment configuration
   * @returns Status object with locked state, missing requirements, and test availability
   */
  toStatus(envConfig: EnvConfig): ProviderLockStatus {
    const missingRequirements = this.getRequiredFields(envConfig);
    const locked = missingRequirements.length > 0;
    const canTest = true;

    return {
      locked,
      missingRequirements,
      canTest,
    };
  }
}
