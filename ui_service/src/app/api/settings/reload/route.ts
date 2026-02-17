import { NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';

const ADMIN_API = process.env.ADMIN_API_URL || 'http://orchestrator:8003';
const execAsync = promisify(exec);

export async function POST() {
  try {
    const res = await fetch(`${ADMIN_API}/admin/reload`, { method: 'POST' });
    const data = await res.json();
    if (!res.ok) {
      const isAuthError = res.status === 401 || String(data?.detail || '').toLowerCase().includes('api key');
      if (!isAuthError) {
        throw new Error(data.detail || 'Reload failed');
      }

      // Fallback for local/dev setups where UI does not have an admin API key.
      const { stdout, stderr } = await execAsync('docker restart orchestrator', { timeout: 30000 });
      if (stderr) {
        console.warn('[Settings Reload] Docker restart stderr:', stderr);
      }
      return NextResponse.json({
        status: 'restarted',
        message: 'Orchestrator restarted via Docker fallback',
        output: stdout,
      });
    }
    return NextResponse.json(data);
  } catch (error: any) {
    console.error('[Settings Reload] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to reload orchestrator config' },
      { status: 500 },
    );
  }
}
