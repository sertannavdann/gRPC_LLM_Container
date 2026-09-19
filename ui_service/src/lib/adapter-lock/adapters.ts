/**
 * Concrete adapter lock/unlock implementations
 *
 * Each adapter subclass defines required credential fields
 * and implements adapter-specific connection testing.
 * Credentials are written to the dashboard credential store — no .env file manipulation.
 */

import {
  AdapterUnlockBase,
  DASHBOARD_SERVICE,
  FieldDefinition,
  ConnectionTestResult,
  CredentialConfig,
} from './base';

/**
 * Weather adapter (OpenWeather) unlock handler.
 */
export class WeatherAdapterLock extends AdapterUnlockBase {
  constructor() {
    super('weather', 'weather/openweather');
  }

  getRequiredFields(): FieldDefinition[] {
    return [
      { name: 'api_key', label: 'OpenWeather API Key', type: 'password', required: true },
      { name: 'city', label: 'City (optional, e.g. Toronto,CA)', type: 'text', required: false },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const apiKey = credentials.api_key;
    if (!apiKey) {
      return { success: false, message: 'OpenWeather API key is required' };
    }

    // The adapter reads settings["city"]; probe the same city the user configured.
    const city = credentials.city || 'Toronto,CA';
    const start = Date.now();

    try {
      const res = await fetch(
        `https://api.openweathermap.org/data/2.5/weather?q=${encodeURIComponent(city)}&appid=${apiKey}&units=metric`,
        { signal: AbortSignal.timeout(10000) }
      );

      const latencyMs = Date.now() - start;

      if (!res.ok) {
        return {
          success: false,
          message: `OpenWeather API error: ${res.status} ${res.statusText}`,
          latencyMs,
        };
      }

      return {
        success: true,
        message: 'OpenWeather connection successful',
        latencyMs,
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        latencyMs: Date.now() - start,
      };
    }
  }
}

/**
 * Calendar adapter (Google Calendar) unlock handler.
 */
export class CalendarAdapterLock extends AdapterUnlockBase {
  constructor() {
    super('calendar', 'calendar/google_calendar');
  }

  getRequiredFields(): FieldDefinition[] {
    return [
      { name: 'access_token', label: 'Google OAuth2 Access Token', type: 'password', required: true },
      { name: 'calendar_id', label: 'Calendar ID', type: 'text', required: true },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const token = credentials.access_token;
    if (!token) {
      return { success: false, message: 'Google OAuth2 token is required' };
    }

    const start = Date.now();

    try {
      const res = await fetch(
        'https://www.googleapis.com/calendar/v3/users/me/calendarList?maxResults=1',
        {
          headers: { Authorization: `Bearer ${token}` },
          signal: AbortSignal.timeout(10000),
        }
      );

      const latencyMs = Date.now() - start;

      if (!res.ok) {
        return {
          success: false,
          message: `Google Calendar API error: ${res.status} ${res.statusText}`,
          latencyMs,
        };
      }

      return {
        success: true,
        message: 'Google Calendar connection successful',
        latencyMs,
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        latencyMs: Date.now() - start,
      };
    }
  }
}

/**
 * Finance adapter (CIBC CSV) unlock handler.
 * CIBC needs no auth: CSV exports are uploaded via POST /bank/upload on the
 * dashboard (UI: /api/dashboard/finance/upload), so the adapter is never locked.
 */
export class FinanceAdapterLock extends AdapterUnlockBase {
  constructor() {
    super('finance', 'finance/cibc');
  }

  getRequiredFields(): FieldDefinition[] {
    return [];
  }

  isLocked(): boolean {
    return false;
  }

  async testConnection(): Promise<ConnectionTestResult> {
    // Finance adapter validates at the backend — we check if the dashboard
    // can serve bank data through the API proxy
    const start = Date.now();

    try {
      const res = await fetch(`${DASHBOARD_SERVICE}/bank/summary`, {
        signal: AbortSignal.timeout(10000),
      });

      const latencyMs = Date.now() - start;

      if (!res.ok) {
        return {
          success: false,
          message: `Finance API error: ${res.status} ${res.statusText}`,
          latencyMs,
        };
      }

      return {
        success: true,
        message: 'Finance data source connected',
        latencyMs,
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        latencyMs: Date.now() - start,
      };
    }
  }
}

/**
 * Gaming adapter (Clash Royale) unlock handler.
 */
export class GamingAdapterLock extends AdapterUnlockBase {
  constructor() {
    super('gaming', 'gaming/clashroyale');
  }

  getRequiredFields(): FieldDefinition[] {
    return [
      { name: 'api_key', label: 'Clash Royale API Key', type: 'password', required: true },
      { name: 'player_tag', label: 'Player Tag (e.g. #ABC123)', type: 'text', required: true },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const apiKey = credentials.api_key;
    const playerTag = credentials.player_tag;

    if (!apiKey) {
      return { success: false, message: 'Clash Royale API key is required' };
    }
    if (!playerTag) {
      return { success: false, message: 'Player tag is required' };
    }

    const start = Date.now();
    const encodedTag = encodeURIComponent(playerTag);

    try {
      const res = await fetch(
        `https://api.clashroyale.com/v1/players/${encodedTag}`,
        {
          headers: { Authorization: `Bearer ${apiKey}` },
          signal: AbortSignal.timeout(10000),
        }
      );

      const latencyMs = Date.now() - start;

      if (!res.ok) {
        return {
          success: false,
          message: `Clash Royale API error: ${res.status} ${res.statusText}`,
          latencyMs,
        };
      }

      return {
        success: true,
        message: 'Clash Royale connection successful',
        latencyMs,
      };
    } catch (error: any) {
      return {
        success: false,
        message: `Connection failed: ${error.message}`,
        latencyMs: Date.now() - start,
      };
    }
  }
}

/**
 * Factory function to get adapter lock handler by module ID or adapter name.
 */
export function getAdapterLockHandler(id: string): AdapterUnlockBase | null {
  const key = id.toLowerCase();
  switch (key) {
    case 'weather':
    case 'weather/openweather':
      return new WeatherAdapterLock();
    case 'calendar':
    case 'calendar/google_calendar':
      return new CalendarAdapterLock();
    case 'finance':
    case 'finance/cibc':
      return new FinanceAdapterLock();
    case 'gaming':
    case 'gaming/clashroyale':
      return new GamingAdapterLock();
    default:
      return null;
  }
}
