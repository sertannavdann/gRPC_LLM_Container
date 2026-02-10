/**
 * Dashboard Adapters API
 *
 * Lists available adapters and manages adapter connections.
 * Reads .env file to determine real connected status based on API keys.
 */
import { NextRequest, NextResponse } from 'next/server';
import { readFileSync, writeFileSync, existsSync } from 'fs';

const ENV_PATH = process.env.ENV_FILE_PATH || '/app/.env';
const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard:8001';

function parseEnvFile(content: string): Record<string, string> {
  const result: Record<string, string> = {};
  for (const line of content.split('\n')) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith('#')) continue;
    const eqIndex = trimmed.indexOf('=');
    if (eqIndex === -1) continue;
    result[trimmed.substring(0, eqIndex).trim()] = trimmed.substring(eqIndex + 1).trim();
  }
  return result;
}

function getEnvConfig(): Record<string, string> {
  if (existsSync(ENV_PATH)) {
    return parseEnvFile(readFileSync(ENV_PATH, 'utf-8'));
  }
  return {};
}

type AdapterDef = {
  platform: string;
  name: string;
  icon: string;
  auth_type: 'api_key' | 'oauth2' | 'none';
  auth_fields: { key: string; label: string; placeholder: string; type: string; envVar: string }[];
  isConnected: (env: Record<string, string>) => boolean;
};

const ADAPTER_DEFINITIONS: Record<string, AdapterDef[]> = {
  finance: [
    {
      platform: 'cibc',
      name: 'CIBC',
      icon: '🏛️',
      auth_type: 'none',
      auth_fields: [],
      isConnected: () => true, // CSV-based, always available
    },
  ],
  calendar: [
    {
      platform: 'mock',
      name: 'Mock Calendar',
      icon: '📅',
      auth_type: 'none',
      auth_fields: [],
      isConnected: () => true,
    },
    {
      platform: 'google_calendar',
      name: 'Google Calendar',
      icon: '📆',
      auth_type: 'oauth2',
      auth_fields: [
        { key: 'googleCalendarClientId', label: 'Client ID', placeholder: 'xxxx.apps.googleusercontent.com', type: 'text', envVar: 'GOOGLE_CALENDAR_CLIENT_ID' },
        { key: 'googleCalendarClientSecret', label: 'Client Secret', placeholder: 'GOCSPX-...', type: 'api_key', envVar: 'GOOGLE_CALENDAR_CLIENT_SECRET' },
        { key: 'googleCalendarAccessToken', label: 'Access Token', placeholder: 'ya29...', type: 'oauth_token', envVar: 'GOOGLE_CALENDAR_ACCESS_TOKEN' },
        { key: 'googleCalendarRefreshToken', label: 'Refresh Token', placeholder: '1//...', type: 'oauth_token', envVar: 'GOOGLE_CALENDAR_REFRESH_TOKEN' },
      ],
      isConnected: (env) => !!(env.GOOGLE_CALENDAR_ACCESS_TOKEN && env.GOOGLE_CALENDAR_REFRESH_TOKEN),
    },
  ],
  health: [
    {
      platform: 'mock',
      name: 'Mock Health',
      icon: '❤️',
      auth_type: 'none',
      auth_fields: [],
      isConnected: () => true,
    },
  ],
  navigation: [
    {
      platform: 'mock',
      name: 'Mock Navigation',
      icon: '🗺️',
      auth_type: 'none',
      auth_fields: [],
      isConnected: () => true,
    },
  ],
  weather: [
    {
      platform: 'openweather',
      name: 'OpenWeather',
      icon: '🌤️',
      auth_type: 'api_key',
      auth_fields: [
        { key: 'openweatherApiKey', label: 'API Key', placeholder: 'Your OpenWeather API key', type: 'api_key', envVar: 'OPENWEATHER_API_KEY' },
        { key: 'openweatherCity', label: 'City', placeholder: 'Toronto,CA', type: 'text', envVar: 'OPENWEATHER_CITY' },
      ],
      isConnected: (env) => !!env.OPENWEATHER_API_KEY,
    },
  ],
  gaming: [
    {
      platform: 'clashroyale',
      name: 'Clash Royale',
      icon: '⚔️',
      auth_type: 'api_key',
      auth_fields: [
        { key: 'clashroyaleApiKey', label: 'API Key', placeholder: 'Your Clash Royale API key', type: 'api_key', envVar: 'CLASH_ROYALE_API_KEY' },
        { key: 'clashroyalePlayerTag', label: 'Player Tag', placeholder: '#ABC123', type: 'text', envVar: 'CLASH_ROYALE_PLAYER_TAG' },
      ],
      isConnected: (env) => !!(env.CLASH_ROYALE_API_KEY && env.CLASH_ROYALE_PLAYER_TAG),
    },
  ],
};

const CATEGORY_ICONS: Record<string, string> = {
  finance: '💰',
  calendar: '📅',
  health: '❤️',
  navigation: '🗺️',
  weather: '🌤️',
  gaming: '🎮',
};

// GET - List available adapters with real connected status
export async function GET(request: NextRequest) {
  try {
    const env = getEnvConfig();
    const searchParams = request.nextUrl.searchParams;
    const category = searchParams.get('category');

    const buildAdapters = (defs: AdapterDef[]) =>
      defs.map((d) => ({
        platform: d.platform,
        name: d.name,
        icon: d.icon,
        connected: d.isConnected(env),
        status: d.isConnected(env) ? ('active' as const) : ('available' as const),
        auth_type: d.auth_type,
        auth_fields: d.auth_fields,
      }));

    if (category && category in ADAPTER_DEFINITIONS) {
      const adapters = buildAdapters(ADAPTER_DEFINITIONS[category]);
      return NextResponse.json({ category, adapters });
    }

    const allCategories = Object.entries(ADAPTER_DEFINITIONS).map(([cat, defs]) => {
      const adapters = buildAdapters(defs);
      return {
        category: cat,
        icon: CATEGORY_ICONS[cat] || '📦',
        adapters,
        connected_count: adapters.filter((a) => a.connected).length,
      };
    });

    return NextResponse.json({
      categories: allCategories,
      total_connected: allCategories.reduce((s, c) => s + c.connected_count, 0),
      total_available: allCategories.reduce((s, c) => s + c.adapters.length, 0),
    });
  } catch (error: any) {
    console.error('[Adapters API] Error:', error);
    return NextResponse.json({ error: error.message || 'Failed to list adapters' }, { status: 500 });
  }
}

// POST - Connect/disconnect adapter by updating .env keys
export async function POST(request: NextRequest) {
  try {
    const body = await request.json();
    const { category, platform, action, credentials } = body;

    if (!category || !platform || !action) {
      return NextResponse.json(
        { error: 'Missing required fields: category, platform, action' },
        { status: 400 }
      );
    }

    if (!['connect', 'disconnect'].includes(action)) {
      return NextResponse.json({ error: 'Invalid action' }, { status: 400 });
    }

    // Find the adapter definition
    const defs = ADAPTER_DEFINITIONS[category];
    if (!defs) {
      return NextResponse.json({ error: `Unknown category: ${category}` }, { status: 400 });
    }
    const adapterDef = defs.find((d) => d.platform === platform);
    if (!adapterDef) {
      return NextResponse.json({ error: `Unknown adapter: ${platform}` }, { status: 400 });
    }

    if (action === 'connect' && credentials) {
      // Write credentials to .env
      let envConfig: Record<string, string> = {};
      if (existsSync(ENV_PATH)) {
        envConfig = parseEnvFile(readFileSync(ENV_PATH, 'utf-8'));
      }

      for (const field of adapterDef.auth_fields) {
        const value = credentials[field.key];
        if (value !== undefined && value !== '') {
          envConfig[field.envVar] = value;
        }
      }

      // Write back
      const lines = ['# gRPC LLM Agent Framework - Environment Configuration', '# Auto-generated by UI settings', ''];
      for (const [k, v] of Object.entries(envConfig)) {
        if (v) lines.push(`${k}=${v}`);
      }
      writeFileSync(ENV_PATH, lines.join('\n') + '\n', 'utf-8');

      console.log(`[Adapters API] Connected ${category}/${platform}`);

      // Hot-reload credentials to dashboard_service (no container restart needed)
      let hotReloadOk = false;
      try {
        // Build credential/settings maps matching dashboard_service env var naming
        const credMap: Record<string, string> = {};
        const settingsMap: Record<string, string> = {};
        for (const field of adapterDef.auth_fields) {
          const value = credentials[field.key];
          if (!value) continue;
          if (field.type === 'text') {
            settingsMap[field.key.replace(/^[a-z]+/, '').replace(/^[A-Z]/, c => c.toLowerCase())] = value;
          } else {
            // Derive short key: openweatherApiKey -> api_key, clashroyalePlayerTag -> player_tag
            const shortKey = field.envVar.split('_').slice(field.envVar.startsWith('GOOGLE') ? 2 : 1).join('_').toLowerCase();
            credMap[shortKey] = value;
          }
        }

        const hotReloadRes = await fetch(`${DASHBOARD_SERVICE}/admin/credentials?user_id=default`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category, platform, credentials: credMap, settings: settingsMap }),
          signal: AbortSignal.timeout(5000),
        });
        hotReloadOk = hotReloadRes.ok;
        if (hotReloadOk) {
          console.log(`[Adapters API] Hot-reloaded credentials for ${platform}`);
        } else {
          console.warn(`[Adapters API] Hot-reload failed: ${hotReloadRes.status}`);
        }
      } catch (err) {
        console.warn('[Adapters API] Hot-reload unavailable:', (err as Error).message);
      }

      return NextResponse.json({
        success: true,
        action,
        category,
        platform,
        message: hotReloadOk
          ? `Connected ${adapterDef.name}. Dashboard will refresh automatically.`
          : `Connected ${adapterDef.name}. Run: docker compose restart dashboard to activate.`,
        restartRequired: !hotReloadOk,
        hotReloaded: hotReloadOk,
      });
    }

    if (action === 'disconnect') {
      // Remove credentials from .env
      let envConfig: Record<string, string> = {};
      if (existsSync(ENV_PATH)) {
        envConfig = parseEnvFile(readFileSync(ENV_PATH, 'utf-8'));
      }

      for (const field of adapterDef.auth_fields) {
        delete envConfig[field.envVar];
      }

      const lines = ['# gRPC LLM Agent Framework - Environment Configuration', '# Auto-generated by UI settings', ''];
      for (const [k, v] of Object.entries(envConfig)) {
        if (v) lines.push(`${k}=${v}`);
      }
      writeFileSync(ENV_PATH, lines.join('\n') + '\n', 'utf-8');

      console.log(`[Adapters API] Disconnected ${category}/${platform}`);

      // Hot-reload disconnect to dashboard_service
      try {
        await fetch(`${DASHBOARD_SERVICE}/admin/disconnect?user_id=default`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ category, platform, credentials: {}, settings: {} }),
          signal: AbortSignal.timeout(5000),
        });
      } catch (err) {
        console.warn('[Adapters API] Disconnect hot-reload unavailable:', (err as Error).message);
      }

      return NextResponse.json({
        success: true,
        action,
        category,
        platform,
        message: `Disconnected ${adapterDef.name}.`,
      });
    }

    // Connect without credentials - return needed fields
    return NextResponse.json({
      success: false,
      action,
      category,
      platform,
      message: 'Credentials required to connect.',
      auth_fields: adapterDef.auth_fields,
    });
  } catch (error: any) {
    console.error('[Adapters API] Error:', error);
    return NextResponse.json({ error: error.message || 'Failed to update adapter' }, { status: 500 });
  }
}
