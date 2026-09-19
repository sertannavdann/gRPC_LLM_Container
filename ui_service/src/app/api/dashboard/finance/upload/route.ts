/**
 * Finance CSV Upload API Route
 *
 * Forwards a multipart CSV upload (form field "file") to dashboard_service
 * POST /bank/upload, which validates it (.csv only, <= 10 MB), stores it and
 * reloads the bank cache. Upstream JSON and status are returned as-is:
 *   success -> { success: true, file: "<name>", transactions: <int> }
 *   error   -> FastAPI { detail: "..." } with a 4xx/5xx status
 */
import { NextRequest, NextResponse } from 'next/server';

const DASHBOARD_SERVICE = process.env.DASHBOARD_SERVICE_URL || 'http://dashboard:8001';
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || process.env.X_API_KEY || '';

export async function POST(request: NextRequest) {
  try {
    const incoming = await request.formData();
    const file = incoming.get('file');
    if (!file || typeof file === 'string') {
      return NextResponse.json({ detail: 'Missing "file" form field' }, { status: 400 });
    }

    const upstreamForm = new FormData();
    upstreamForm.append('file', file, file.name);

    const res = await fetch(`${DASHBOARD_SERVICE}/bank/upload`, {
      method: 'POST',
      headers: { 'X-API-Key': ADMIN_API_KEY },
      body: upstreamForm,
      signal: AbortSignal.timeout(30000),
      cache: 'no-store',
    });

    const text = await res.text();
    let payload: unknown;
    try {
      payload = JSON.parse(text);
    } catch {
      payload = { detail: text || `Dashboard returned HTTP ${res.status}` };
    }
    return NextResponse.json(payload, { status: res.status });
  } catch (error: any) {
    console.error('[Finance Upload API] Error:', error);
    return NextResponse.json(
      { detail: error.message || 'Failed to upload CSV' },
      { status: 500 }
    );
  }
}
