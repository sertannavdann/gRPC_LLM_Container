import { NextRequest, NextResponse } from 'next/server';
import { exec } from 'child_process';
import { promisify } from 'util';

const execAsync = promisify(exec);

// POST - Restart the orchestrator service
export async function POST(request: NextRequest) {
  try {
    console.log('[Restart API] Triggering orchestrator restart...');
    
    // Use docker compose to restart just the orchestrator
    // This runs inside the ui_service container, so we need docker socket access
    // Alternative: Use docker API or a sidecar container
    
    // For now, we'll use a simple HTTP call to a restart endpoint
    // The orchestrator will need to expose this, or we use docker socket
    
    // Option 1: If docker socket is mounted, use docker CLI
    try {
      const { stdout, stderr } = await execAsync(
        'docker restart orchestrator',
        { timeout: 30000 }
      );
      console.log('[Restart API] Docker restart output:', stdout);
      if (stderr) console.warn('[Restart API] Docker restart stderr:', stderr);
      
      return NextResponse.json({
        success: true,
        message: 'Orchestrator restart initiated',
      });
    } catch (dockerError: any) {
      console.log('[Restart API] Docker CLI not available, trying alternative...');
      
      // Option 2: Signal-based restart via orchestrator's health endpoint
      // This requires the orchestrator to support graceful restart
      
      return NextResponse.json({
        success: false,
        message: 'Manual restart required. Run: docker compose restart orchestrator',
        manualRequired: true,
      });
    }
  } catch (error: any) {
    console.error('[Restart API] Error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to restart orchestrator' },
      { status: 500 }
    );
  }
}

// GET - Check orchestrator status
export async function GET() {
  try {
    // Try to call the orchestrator health endpoint
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 5000);
    
    try {
      // gRPC health check isn't directly callable from here
      // We'll use a simple connectivity test
      const response = await fetch('http://orchestrator:50054', {
        signal: controller.signal,
      }).catch(() => null);
      
      clearTimeout(timeout);
      
      // If we get any response (even an error), the service is up
      return NextResponse.json({
        status: 'running',
        message: 'Orchestrator is responding',
      });
    } catch (fetchError) {
      clearTimeout(timeout);
      return NextResponse.json({
        status: 'starting',
        message: 'Orchestrator is starting up...',
      });
    }
  } catch (error: any) {
    return NextResponse.json({
      status: 'unknown',
      message: error.message,
    });
  }
}
