/**
 * Concrete adapter lock/unlock implementations
 *
 * Each adapter subclass defines required credential fields
 * and implements adapter-specific connection testing.
 * Credentials flow through Admin API — no .env file manipulation.
 */

import {
  AdapterUnlockBase,
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
      { name: 'base_url', label: 'Base URL (optional)', type: 'text', required: false },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const apiKey = credentials.api_key;
    if (!apiKey) {
      return { success: false, message: 'OpenWeather API key is required' };
    }

    const baseUrl = credentials.base_url || 'https://api.openweathermap.org/data/2.5';
    const start = Date.now();

    try {
      const res = await fetch(
        `${baseUrl}/weather?q=London&appid=${apiKey}&units=metric`,
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
      { name: 'oauth_token', label: 'Google OAuth2 Token', type: 'password', required: true },
      { name: 'calendar_id', label: 'Calendar ID', type: 'text', required: true },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const token = credentials.oauth_token;
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
 * Supports CSV file path mode (local) or API mode (future).
 */
export class FinanceAdapterLock extends AdapterUnlockBase {
  constructor() {
    super('finance', 'finance/cibc');
  }

  getRequiredFields(): FieldDefinition[] {
    return [
      { name: 'csv_path', label: 'CSV File Path', type: 'text', required: true },
    ];
  }

  async testConnection(credentials: CredentialConfig): Promise<ConnectionTestResult> {
    const csvPath = credentials.csv_path;
    if (!csvPath) {
      return { success: false, message: 'CSV file path is required' };
    }

    // Finance adapter validates at the backend — we check if the dashboard
    // can serve bank data through the API proxy
    const start = Date.now();

    try {
      const dashboardUrl = process.env.DASHBOARD_URL || 'http://localhost:8001';
      const res = await fetch(`${dashboardUrl}/bank/summary`, {
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
