/**
 * Adapter registry API route
 *
 * Reads adapter status from the Admin API module registry (one GET
 * /admin/modules per request; `has_credentials` per module_id).
 * Stores/removes credentials through the dashboard credential store
 * via the adapter-lock handlers — no .env manipulation.
 */

import { NextResponse } from 'next/server';
import { getAdapterLockHandler } from '@/lib/adapter-lock/adapters';
import { fetchCredentialedModuleIds } from '@/lib/adapter-lock/base';

interface AdapterStatus {
  id: string;
  name: string;
  category: string;
  status: 'connected' | 'locked' | 'error';
  requiredFields: { name: string; label: string; type: string; required: boolean }[];
  missingFields: string[];
}

/**
 * GET /api/adapters — List all adapters with lock/unlock status
 */
export async function GET() {
  try {
    // One Admin API call: module_ids that have stored credentials
    const credentialed = await fetchCredentialedModuleIds();

    // Known adapter categories to check
    const knownAdapters = [
      { id: 'weather/openweather', name: 'OpenWeather', category: 'weather' },
      { id: 'calendar/google_calendar', name: 'Google Calendar', category: 'calendar' },
      { id: 'finance/cibc', name: 'CIBC Finance', category: 'finance' },
      { id: 'gaming/clashroyale', name: 'Clash Royale', category: 'gaming' },
    ];

    const results: AdapterStatus[] = [];

    for (const adapter of knownAdapters) {
      const handler = getAdapterLockHandler(adapter.id);
      if (!handler) continue;

      // Credential values are not readable; locked = needs fields and none stored
      const requiredFields = handler.getRequiredFields();
      const requiredNames = requiredFields.filter((f) => f.required).map((f) => f.name);
      const locked = requiredNames.length > 0 && !credentialed.has(adapter.id);

      results.push({
        id: adapter.id,
        name: adapter.name,
        category: adapter.category,
        status: locked ? 'locked' : 'connected',
        requiredFields,
        missingFields: locked ? requiredNames : [],
      });
    }

    return NextResponse.json({ adapters: results });
  } catch (error: any) {
    return NextResponse.json(
      { error: 'Failed to fetch adapter status', details: error.message },
      { status: 500 }
    );
  }
}

/**
 * POST /api/adapters — Store credentials and test connection
 */
export async function POST(request: Request) {
  try {
    const body = await request.json();
    const { adapterId, credentials } = body;

    if (!adapterId || !credentials) {
      return NextResponse.json(
        { error: 'adapterId and credentials are required' },
        { status: 400 }
      );
    }

    const handler = getAdapterLockHandler(adapterId);
    if (!handler) {
      return NextResponse.json(
        { error: `Unknown adapter: ${adapterId}` },
        { status: 404 }
      );
    }

    // Store credentials in the dashboard credential store
    const stored = await handler.storeCredentials(credentials);
    if (!stored) {
      return NextResponse.json(
        { error: 'Failed to store credentials' },
        { status: 500 }
      );
    }

    // Test connection with new credentials
    const testResult = await handler.testConnection(credentials);

    return NextResponse.json({
      adapterId,
      stored: true,
      connectionTest: testResult,
    });
  } catch (error: any) {
    return NextResponse.json(
      { error: 'Failed to store credentials', details: error.message },
      { status: 500 }
    );
  }
}

/**
 * DELETE /api/adapters — Remove adapter credentials
 */
export async function DELETE(request: Request) {
  try {
    const body = await request.json();
    const { adapterId } = body;

    if (!adapterId) {
      return NextResponse.json(
        { error: 'adapterId is required' },
        { status: 400 }
      );
    }

    const handler = getAdapterLockHandler(adapterId);
    if (!handler) {
      return NextResponse.json(
        { error: `Unknown adapter: ${adapterId}` },
        { status: 404 }
      );
    }

    // Remove credentials from the dashboard credential store
    const removed = await handler.deleteCredentials();
    if (!removed) {
      return NextResponse.json(
        { error: 'Failed to remove credentials' },
        { status: 500 }
      );
    }

    return NextResponse.json({ adapterId, removed: true });
  } catch (error: any) {
    return NextResponse.json(
      { error: 'Failed to remove credentials', details: error.message },
      { status: 500 }
    );
  }
}
