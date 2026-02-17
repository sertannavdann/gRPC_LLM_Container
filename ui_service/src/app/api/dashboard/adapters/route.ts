/**
 * Dashboard Adapters API
 *
 * Lists available adapters and manages adapter connections.
 * Credentials flow through Admin API — no .env file manipulation.
 */
import { NextRequest, NextResponse } from 'next/server';
import { getAdapterLockHandler } from '@/lib/adapter-lock/adapters';
import type { CredentialConfig } from '@/lib/adapter-lock/base';

const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard:8001';

type AdapterDef = {
  platform: string;
  name: string;
  icon: string;
  moduleId: string;
  auth_type: 'api_key' | 'oauth2' | 'none';
  auth_fields: { key: string; label: string; placeholder: string; type: string; credentialKey: string }[];
  alwaysConnected?: boolean;
};

const ADAPTER_DEFINITIONS: Record<string, AdapterDef[]> = {
  finance: [
    {
      platform: 'cibc',
      name: 'CIBC',
      icon: '🏛️',
      moduleId: 'finance/cibc',
      auth_type: 'none',
      auth_fields: [],
      alwaysConnected: true,
    },
  ],
  calendar: [
    {
      platform: 'mock',
      name: 'Mock Calendar',
      icon: '📅',
      moduleId: 'calendar/mock',
      auth_type: 'none',
      auth_fields: [],
      alwaysConnected: true,
    },
    {
      platform: 'google_calendar',
      name: 'Google Calendar',
      icon: '📆',
      moduleId: 'calendar/google_calendar',
      auth_type: 'oauth2',
      auth_fields: [
        { key: 'googleCalendarClientId', label: 'Client ID', placeholder: 'xxxx.apps.googleusercontent.com', type: 'text', credentialKey: 'client_id' },
        { key: 'googleCalendarClientSecret', label: 'Client Secret', placeholder: 'GOCSPX-...', type: 'api_key', credentialKey: 'client_secret' },
        { key: 'googleCalendarAccessToken', label: 'Access Token', placeholder: 'ya29...', type: 'oauth_token', credentialKey: 'oauth_token' },
        { key: 'googleCalendarRefreshToken', label: 'Refresh Token', placeholder: '1//...', type: 'oauth_token', credentialKey: 'refresh_token' },
      ],
    },
  ],
  health: [
    {
      platform: 'mock',
      name: 'Mock Health',
      icon: '❤️',
      moduleId: 'health/mock',
      auth_type: 'none',
      auth_fields: [],
      alwaysConnected: true,
    },
  ],
  navigation: [
    {
      platform: 'mock',
      name: 'Mock Navigation',
      icon: '🗺️',
      moduleId: 'navigation/mock',
      auth_type: 'none',
      auth_fields: [],
      alwaysConnected: true,
    },
  ],
  weather: [
    {
      platform: 'openweather',
      name: 'OpenWeather',
      icon: '🌤️',
      moduleId: 'weather/openweather',
      auth_type: 'api_key',
      auth_fields: [
        { key: 'openweatherApiKey', label: 'API Key', placeholder: 'Your OpenWeather API key', type: 'api_key', credentialKey: 'api_key' },
        { key: 'openweatherCity', label: 'City', placeholder: 'Toronto,CA', type: 'text', credentialKey: 'base_url' },
      ],
    },
  ],
  gaming: [
    {
      platform: 'clashroyale',
      name: 'Clash Royale',
      icon: '⚔️',
      moduleId: 'gaming/clashroyale',
      auth_type: 'api_key',
      auth_fields: [
        { key: 'clashroyaleApiKey', label: 'API Key', placeholder: 'Your Clash Royale API key', type: 'api_key', credentialKey: 'api_key' },
        { key: 'clashroyalePlayerTag', label: 'Player Tag', placeholder: '#ABC123', type: 'text', credentialKey: 'player_tag' },
      ],
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

// GET - List available adapters with real connected status from Admin API
export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const category = searchParams.get('category');

    const buildAdapters = async (defs: AdapterDef[]) => {
      const results = [];
      for (const d of defs) {
        let connected = false;
        if (d.alwaysConnected) {
          connected = true;
        } else {
          const handler = getAdapterLockHandler(d.moduleId);
          if (handler) {
            const credentials = await handler.fetchCredentials();
            connected = !handler.isLocked(credentials);
          }
        }
        results.push({
          platform: d.platform,
          name: d.name,
          icon: d.icon,
          connected,
          status: connected ? ('active' as const) : ('available' as const),
          auth_type: d.auth_type,
          auth_fields: d.auth_fields,
        });
      }
      return results;
    };

    if (category && category in ADAPTER_DEFINITIONS) {
      const adapters = await buildAdapters(ADAPTER_DEFINITIONS[category]);
      return NextResponse.json({ category, adapters });
    }

    const allCategories = [];
    for (const [cat, defs] of Object.entries(ADAPTER_DEFINITIONS)) {
      const adapters = await buildAdapters(defs);
      allCategories.push({
        category: cat,
        icon: CATEGORY_ICONS[cat] || '📦',
        adapters,
        connected_count: adapters.filter((a) => a.connected).length,
      });
    }

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

// POST - Connect/disconnect adapter via Admin API credential store
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

    const handler = getAdapterLockHandler(adapterDef.moduleId);

    if (action === 'connect' && credentials) {
      // Map UI credential keys to Admin API credential keys
      const credentialMap: Record<string, string> = {};
      for (const field of adapterDef.auth_fields) {
        const value = credentials[field.key];
        if (value !== undefined && value !== '') {
          credentialMap[field.credentialKey] = value;
        }
      }

      // Store credentials via Admin API
      if (handler) {
        const stored = await handler.storeCredentials(credentialMap);
        if (!stored) {
          console.warn(`[Adapters API] Admin API store failed for ${platform}, falling back to hot-reload`);
        }
      }

      console.log(`[Adapters API] Connected ${category}/${platform} via Admin API`);

      // Hot-reload credentials to dashboard_service (no container restart needed)
      let hotReloadOk = false;
      try {
        const credMap: Record<string, string> = {};
        const settingsMap: Record<string, string> = {};
        for (const field of adapterDef.auth_fields) {
          const value = credentials[field.key];
          if (!value) continue;
          if (field.type === 'text') {
            settingsMap[field.credentialKey] = value;
          } else {
            credMap[field.credentialKey] = value;
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
      // Remove credentials via Admin API
      if (handler) {
        try {
          const ADMIN_API_BASE = process.env.ADMIN_API_URL || 'http://localhost:8003';
          await fetch(
            `${ADMIN_API_BASE}/admin/modules/${encodeURIComponent(adapterDef.moduleId)}/credentials`,
            { method: 'DELETE' }
          );
        } catch (err) {
          console.warn(`[Adapters API] Admin API delete failed for ${platform}:`, (err as Error).message);
        }
      }

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
