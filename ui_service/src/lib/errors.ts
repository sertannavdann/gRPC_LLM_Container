/**
 * Error Taxonomy
 *
 * Standardized error classification for the NEXUS UI.
 * Maps HTTP status codes and error shapes to 5 error types.
 * isRetryable maps to XState isRetryableError guard for auto-retry decisions.
 *
 * Error types:
 *   NOT_AUTHORIZED - 401/403 responses
 *   NOT_CONFIGURED - 404 on provider/adapter + missing config
 *   DEGRADED_PROVIDER - 502/503 on provider endpoint
 *   TOOL_SCHEMA_MISMATCH - JSON parse error or unexpected response shape
 *   TIMEOUT - AbortError or timeout
 *
 * Academic anchor: EDMO T1 (resilience theme — failure-mode-pattern fit)
 */

// ── Error Types ─────────────────────────────────────────────────────────────

export enum NexusErrorType {
  NOT_AUTHORIZED = 'NOT_AUTHORIZED',
  NOT_CONFIGURED = 'NOT_CONFIGURED',
  DEGRADED_PROVIDER = 'DEGRADED_PROVIDER',
  TOOL_SCHEMA_MISMATCH = 'TOOL_SCHEMA_MISMATCH',
  TIMEOUT = 'TIMEOUT',
}

// ── Error Classification ────────────────────────────────────────────────────

/**
 * Classify an unknown error into a NexusErrorType.
 * Maps HTTP status codes, error names, and error messages to types.
 */
export function classifyError(error: unknown): NexusErrorType {
  // Handle fetch Response-like errors with status codes
  if (error && typeof error === 'object') {
    const err = error as Record<string, unknown>;

    // Check for status code (from fetch errors or custom error objects)
    const status = err.status ?? err.statusCode;
    if (typeof status === 'number') {
      if (status === 401 || status === 403) {
        return NexusErrorType.NOT_AUTHORIZED;
      }
      if (status === 404) {
        return NexusErrorType.NOT_CONFIGURED;
      }
      if (status === 502 || status === 503) {
        return NexusErrorType.DEGRADED_PROVIDER;
      }
      if (status === 408 || status === 504) {
        return NexusErrorType.TIMEOUT;
      }
    }

    // Check for AbortError (fetch timeout)
    if (err.name === 'AbortError' || err.name === 'TimeoutError') {
      return NexusErrorType.TIMEOUT;
    }

    // Check for TypeError from JSON.parse failures
    if (err.name === 'SyntaxError' || err.name === 'TypeError') {
      return NexusErrorType.TOOL_SCHEMA_MISMATCH;
    }
  }

  // Check error message patterns
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();

    if (msg.includes('unauthorized') || msg.includes('forbidden') || msg.includes('401') || msg.includes('403')) {
      return NexusErrorType.NOT_AUTHORIZED;
    }
    if (msg.includes('not found') || msg.includes('not configured') || msg.includes('missing config') || msg.includes('404')) {
      return NexusErrorType.NOT_CONFIGURED;
    }
    if (msg.includes('502') || msg.includes('503') || msg.includes('bad gateway') || msg.includes('service unavailable')) {
      return NexusErrorType.DEGRADED_PROVIDER;
    }
    if (msg.includes('timeout') || msg.includes('timed out') || msg.includes('aborted') || msg.includes('abort')) {
      return NexusErrorType.TIMEOUT;
    }
    if (msg.includes('json') || msg.includes('parse') || msg.includes('unexpected') || msg.includes('schema')) {
      return NexusErrorType.TOOL_SCHEMA_MISMATCH;
    }
  }

  // Default: treat unknown errors as provider degradation
  return NexusErrorType.DEGRADED_PROVIDER;
}

// ── Retry Policy ────────────────────────────────────────────────────────────

/**
 * Determine if an error type is retryable.
 * Maps to XState isRetryableError guard for auto-retry decisions.
 *
 * Retryable: TIMEOUT, DEGRADED_PROVIDER (transient errors)
 * Not retryable: NOT_AUTHORIZED, NOT_CONFIGURED, TOOL_SCHEMA_MISMATCH (permanent errors)
 */
export function isRetryable(type: NexusErrorType): boolean {
  return type === NexusErrorType.TIMEOUT || type === NexusErrorType.DEGRADED_PROVIDER;
}

// ── User-Friendly Messages ──────────────────────────────────────────────────

/**
 * Return a user-friendly error message for each error type.
 */
export function errorMessage(type: NexusErrorType): string {
  switch (type) {
    case NexusErrorType.NOT_AUTHORIZED:
      return 'You are not authorized to access this resource. Please check your API key or permissions.';
    case NexusErrorType.NOT_CONFIGURED:
      return 'This feature is not configured yet. Please set up the required provider or adapter in Settings.';
    case NexusErrorType.DEGRADED_PROVIDER:
      return 'The service is experiencing issues. The system will retry automatically.';
    case NexusErrorType.TOOL_SCHEMA_MISMATCH:
      return 'Received an unexpected response format. This may indicate a version mismatch.';
    case NexusErrorType.TIMEOUT:
      return 'The request timed out. The system will retry automatically.';
    default:
      return 'An unexpected error occurred.';
  }
}
