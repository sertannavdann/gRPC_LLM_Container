import { NextRequest, NextResponse } from 'next/server';
import { readFileSync, existsSync } from 'fs';
import { getProviderUnlockHandler } from '@/lib/provider-lock/providers';

// Path to .env file in the root workspace
const ENV_PATH = process.env.ENV_FILE_PATH || '/app/.env';

function parseEnvFile(content: string): Record<string, string> {
  const result: Record<string, string> = {};
  const lines = content.split('\n');

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;

    const eqIndex = trimmed.indexOf('=');
    if (eqIndex === -1) continue;

    const key = trimmed.substring(0, eqIndex).trim();
    const value = trimmed.substring(eqIndex + 1).trim();
    result[key] = value;
  }

  return result;
}

/**
 * POST /api/settings/connection-test
 *
 * Test provider connection using unlock handler class.
 * Accepts provider name and optional key overrides for testing before saving.
 */
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { provider, overrides } = body;

    if (!provider || typeof provider !== 'string') {
      return NextResponse.json(
        {
          success: false,
          error: 'Provider name is required',
          message: 'Invalid request: provider field missing or invalid',
        },
        { status: 400 }
      );
    }

    // Get unlock handler for provider
    const handler = getProviderUnlockHandler(provider);
    if (!handler) {
      return NextResponse.json(
        {
          success: false,
          error: 'Unknown provider',
          message: `Provider '${provider}' is not supported`,
        },
        { status: 400 }
      );
    }

    // Load current environment config
    let envConfig: Record<string, string> = {};
    if (existsSync(ENV_PATH)) {
      const content = readFileSync(ENV_PATH, 'utf-8');
      envConfig = parseEnvFile(content);
    }

    // Run connection test
    const result = await handler.testConnection({
      envConfig,
      overrides: overrides || {},
    });

    // Return standardized result
    return NextResponse.json(result);
  } catch (error: any) {
    console.error('[Connection Test API] Error:', error);
    return NextResponse.json(
      {
        success: false,
        message: error.message || 'Connection test failed',
        details: { error: error.message },
      },
      { status: 500 }
    );
  }
}
