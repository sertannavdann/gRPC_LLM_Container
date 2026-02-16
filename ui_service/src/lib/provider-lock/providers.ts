/**
 * Concrete provider unlock implementations
 *
 * Each provider subclass defines required connection prerequisites
 * and implements provider-specific connection testing.
 */

import { ProviderUnlockBase, ConnectionTestResult, EnvConfig } from './base';

/**
 * Local provider unlock handler.
 * Always unlocked - no external API keys required.
 */
export class LocalUnlock extends ProviderUnlockBase {
  constructor() {
    super('local');
  }

  getRequiredFields(_envConfig: EnvConfig): string[] {
    // Local provider has no external requirements
    return [];
  }

  async testConnection(_payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult> {
    // No-op health check for local provider
    return {
      success: true,
      message: 'Local provider is always available',
      details: { provider: 'local' },
    };
  }
}

/**
 * NVIDIA NIM provider unlock handler.
 * Requires API key and base URL for OpenAI-compatible endpoints.
 */
export class NvidiaUnlock extends ProviderUnlockBase {
  constructor() {
    super('nvidia');
  }

  getRequiredFields(envConfig: EnvConfig): string[] {
    const missing: string[] = [];
    if (!envConfig.NIM_API_KEY) missing.push('NIM_API_KEY');
    if (!envConfig.NIM_BASE_URL) missing.push('NIM_BASE_URL');
    return missing;
  }

  async testConnection(payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult> {
    const apiKey = payload.overrides?.apiKey || payload.envConfig.NIM_API_KEY;
    const baseUrl = payload.overrides?.baseUrl || payload.envConfig.NIM_BASE_URL || 'https://integrate.api.nvidia.com/v1';

    if (!apiKey) {
      return {
        success: false,
        message: 'NIM_API_KEY is required',
        details: { provider: 'nvidia', error: 'missing_api_key' },
      };
    }

    try {
      // Lightweight probe: list models endpoint
      const response = await fetch(`${baseUrl}/models`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        return {
          success: false,
          message: `NVIDIA NIM API error: ${response.status} ${response.statusText}`,
          details: {
            provider: 'nvidia',
            status: response.status,
            error: errorText,
          },
        };
      }

      const data = await response.json();
      return {
        success: true,
        message: 'NVIDIA NIM connection successful',
        details: {
          provider: 'nvidia',
          modelsAvailable: data.data?.length || 0,
        },
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        details: {
          provider: 'nvidia',
          error: error.message,
        },
      };
    }
  }
}

/**
 * OpenAI provider unlock handler.
 * Requires API key for OpenAI API.
 */
export class OpenAIUnlock extends ProviderUnlockBase {
  constructor() {
    super('openai');
  }

  getRequiredFields(envConfig: EnvConfig): string[] {
    const missing: string[] = [];
    if (!envConfig.OPENAI_API_KEY) missing.push('OPENAI_API_KEY');
    return missing;
  }

  async testConnection(payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult> {
    const apiKey = payload.overrides?.apiKey || payload.envConfig.OPENAI_API_KEY;
    const baseUrl = payload.overrides?.baseUrl || payload.envConfig.OPENAI_BASE_URL || 'https://api.openai.com/v1';

    if (!apiKey) {
      return {
        success: false,
        message: 'OPENAI_API_KEY is required',
        details: { provider: 'openai', error: 'missing_api_key' },
      };
    }

    try {
      // Lightweight probe: list models endpoint
      const response = await fetch(`${baseUrl}/models`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        return {
          success: false,
          message: `OpenAI API error: ${response.status} ${response.statusText}`,
          details: {
            provider: 'openai',
            status: response.status,
            error: errorText,
          },
        };
      }

      const data = await response.json();
      return {
        success: true,
        message: 'OpenAI connection successful',
        details: {
          provider: 'openai',
          modelsAvailable: data.data?.length || 0,
        },
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        details: {
          provider: 'openai',
          error: error.message,
        },
      };
    }
  }
}

/**
 * Anthropic provider unlock handler.
 * Requires API key for Claude API.
 */
export class AnthropicUnlock extends ProviderUnlockBase {
  constructor() {
    super('anthropic');
  }

  getRequiredFields(envConfig: EnvConfig): string[] {
    const missing: string[] = [];
    if (!envConfig.ANTHROPIC_API_KEY) missing.push('ANTHROPIC_API_KEY');
    return missing;
  }

  async testConnection(payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult> {
    const apiKey = payload.overrides?.apiKey || payload.envConfig.ANTHROPIC_API_KEY;
    const baseUrl = payload.overrides?.baseUrl || payload.envConfig.ANTHROPIC_BASE_URL || 'https://api.anthropic.com/v1';

    if (!apiKey) {
      return {
        success: false,
        message: 'ANTHROPIC_API_KEY is required',
        details: { provider: 'anthropic', error: 'missing_api_key' },
      };
    }

    try {
      // Lightweight probe: minimal message request to validate credentials
      const response = await fetch(`${baseUrl}/messages`, {
        method: 'POST',
        headers: {
          'x-api-key': apiKey,
          'anthropic-version': '2023-06-01',
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'claude-3-haiku-20240307',
          max_tokens: 10,
          messages: [{ role: 'user', content: 'test' }],
        }),
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        return {
          success: false,
          message: `Anthropic API error: ${response.status} ${response.statusText}`,
          details: {
            provider: 'anthropic',
            status: response.status,
            error: errorText,
          },
        };
      }

      return {
        success: true,
        message: 'Anthropic connection successful',
        details: {
          provider: 'anthropic',
          model: 'claude-3-haiku-20240307',
        },
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        details: {
          provider: 'anthropic',
          error: error.message,
        },
      };
    }
  }
}

/**
 * Perplexity provider unlock handler.
 * Requires API key for Perplexity API.
 */
export class PerplexityUnlock extends ProviderUnlockBase {
  constructor() {
    super('perplexity');
  }

  getRequiredFields(envConfig: EnvConfig): string[] {
    const missing: string[] = [];
    if (!envConfig.PERPLEXITY_API_KEY) missing.push('PERPLEXITY_API_KEY');
    return missing;
  }

  async testConnection(payload: {
    envConfig: EnvConfig;
    overrides?: Record<string, string>;
  }): Promise<ConnectionTestResult> {
    const apiKey = payload.overrides?.apiKey || payload.envConfig.PERPLEXITY_API_KEY;
    const baseUrl = payload.overrides?.baseUrl || payload.envConfig.PERPLEXITY_BASE_URL || 'https://api.perplexity.ai';

    if (!apiKey) {
      return {
        success: false,
        message: 'PERPLEXITY_API_KEY is required',
        details: { provider: 'perplexity', error: 'missing_api_key' },
      };
    }

    try {
      // Lightweight probe: minimal chat completion request
      const response = await fetch(`${baseUrl}/chat/completions`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${apiKey}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          model: 'llama-3.1-sonar-small-128k-online',
          messages: [{ role: 'user', content: 'test' }],
          max_tokens: 10,
        }),
        signal: AbortSignal.timeout(10000),
      });

      if (!response.ok) {
        const errorText = await response.text().catch(() => 'Unknown error');
        return {
          success: false,
          message: `Perplexity API error: ${response.status} ${response.statusText}`,
          details: {
            provider: 'perplexity',
            status: response.status,
            error: errorText,
          },
        };
      }

      return {
        success: true,
        message: 'Perplexity connection successful',
        details: {
          provider: 'perplexity',
          model: 'llama-3.1-sonar-small-128k-online',
        },
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        details: {
          provider: 'perplexity',
          error: error.message,
        },
      };
    }
  }
}

/**
 * Factory function to get appropriate unlock handler for a provider.
 * @param providerName - Name of the provider (local/nvidia/openai/anthropic/perplexity)
 * @returns Provider unlock handler instance or null if provider not found
 */
export function getProviderUnlockHandler(providerName: string): ProviderUnlockBase | null {
  switch (providerName.toLowerCase()) {
    case 'local':
      return new LocalUnlock();
    case 'nvidia':
      return new NvidiaUnlock();
    case 'openai':
      return new OpenAIUnlock();
    case 'anthropic':
      return new AnthropicUnlock();
    case 'perplexity':
      return new PerplexityUnlock();
    default:
      return null;
  }
}
