import { NextResponse } from 'next/server';

const ADMIN_API = process.env.ADMIN_API_URL || 'http://orchestrator:8003';

export async function POST() {
  try {
    const res = await fetch(`${ADMIN_API}/admin/reload`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || 'Reload failed');
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('[Settings Reload] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to reload orchestrator config' },
      { status: 500 },
    );
  }
}
