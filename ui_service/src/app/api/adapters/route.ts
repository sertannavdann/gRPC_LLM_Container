/**
 * Adapter registry API route
 *
 * Reads adapter status from Admin API module registry.
 * Stores/removes credentials through Admin API — no .env manipulation.
 */

import { NextResponse } from 'next/server';
import { getAdapterLockHandler } from '@/lib/adapter-lock/adapters';

const ADMIN_API_BASE = process.env.ADMIN_API_URL || 'http://localhost:8003';

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
    // Fetch installed modules from Admin API
    let modules: any[] = [];
    try {
      const res = await fetch(`${ADMIN_API_BASE}/admin/modules`, {
        headers: { 'Content-Type': 'application/json' },
        signal: AbortSignal.timeout(5000),
      });
      if (res.ok) {
        const data = await res.json();
        modules = data.modules || data || [];
      }
    } catch {
      // Admin API unreachable — return known adapters with error status
    }

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

      const credentials = await handler.fetchCredentials();
      const lockStatus = handler.toStatus(credentials);

      results.push({
        id: adapter.id,
        name: adapter.name,
        category: adapter.category,
        status: lockStatus.locked ? 'locked' : 'connected',
        requiredFields: handler.getRequiredFields(),
        missingFields: lockStatus.missingFields,
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

    // Store credentials via Admin API
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

    // Remove credentials via Admin API
    const res = await fetch(
      `${ADMIN_API_BASE}/admin/modules/${encodeURIComponent(adapterId)}/credentials`,
      { method: 'DELETE' }
    );

    if (!res.ok) {
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
