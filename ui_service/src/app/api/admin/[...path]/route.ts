import { NextRequest, NextResponse } from 'next/server';
import {
  ADMIN_REQUEST_TIMEOUT_MS,
  ENABLE_READONLY_FALLBACK,
  FALLBACK_SOURCE,
  type FallbackReason,
  READONLY_FALLBACK_PATHS,
} from '@/lib/runtime-params';

const ADMIN_API_BASE = process.env.ADMIN_API_URL || 'http://orchestrator:8003';
const ADMIN_API_KEY = process.env.ADMIN_API_KEY || process.env.X_API_KEY || '';

const READONLY_FALLBACK_PATH_SET = new Set(READONLY_FALLBACK_PATHS);

const READONLY_CAPABILITIES_PATH = '/admin/capabilities';
const READONLY_FEATURE_HEALTH_PATH = '/admin/feature-health';
const READONLY_CONFIG_VERSION_PATH = '/admin/config/version';

function fallbackCapabilities(reason: FallbackReason) {
  const now = new Date().toISOString();
  return {
    tools: [],
    modules: [],
    providers: [],
    adapters: [],
    features: [],
    config_version: 'local-dev-fallback',
    timestamp: now,
    snapshot_source: FALLBACK_SOURCE,
    fallback_reason: reason,
  };
}

function fallbackFeatureHealth(reason: FallbackReason) {
  return [
    {
      feature: 'capabilities',
      status: 'unknown',
      degraded_reasons: [reason],
      dependencies: ['admin_api_key'],
    },
  ];
}

function fallbackConfigVersion(reason: FallbackReason) {
  return {
    config_version: 'local-dev-fallback',
    fallback_source: FALLBACK_SOURCE,
    fallback_reason: reason,
  };
}

function maybeFallback(upstreamPath: string, reason: FallbackReason) {
  if (!ENABLE_READONLY_FALLBACK || !READONLY_FALLBACK_PATH_SET.has(upstreamPath as (typeof READONLY_FALLBACK_PATHS)[number])) {
    return null;
  }

  if (upstreamPath === READONLY_CAPABILITIES_PATH) {
    return NextResponse.json(fallbackCapabilities(reason), { status: 200 });
  }
  if (upstreamPath === READONLY_FEATURE_HEALTH_PATH) {
    return NextResponse.json(fallbackFeatureHealth(reason), { status: 200 });
  }
  if (upstreamPath === READONLY_CONFIG_VERSION_PATH) {
    const response = NextResponse.json(fallbackConfigVersion(reason), { status: 200 });
    response.headers.set('ETag', '"local-dev-fallback"');
    return response;
  }

  return null;
}

async function handleProxy(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  const params = await ctx.params;
  const pathParts = params.path || [];
  const upstreamPath = `/admin/${pathParts.join('/')}`;

  const upstream = new URL(`${ADMIN_API_BASE}${upstreamPath}`);
  upstream.search = request.nextUrl.search;

  const headers = new Headers();
  const incomingApiKey = request.headers.get('x-api-key');
  const apiKey = incomingApiKey || ADMIN_API_KEY;

  const contentType = request.headers.get('content-type');
  const ifNoneMatch = request.headers.get('if-none-match');
  const accept = request.headers.get('accept');

  if (contentType) headers.set('content-type', contentType);
  if (ifNoneMatch) headers.set('if-none-match', ifNoneMatch);
  if (accept) headers.set('accept', accept);
  if (apiKey) headers.set('x-api-key', apiKey);

  const method = request.method;
  const body = method === 'GET' || method === 'HEAD' ? undefined : await request.text();

  try {
    const res = await fetch(upstream.toString(), {
      method,
      headers,
      body,
      signal: AbortSignal.timeout(ADMIN_REQUEST_TIMEOUT_MS),
      cache: 'no-store',
    });

    if (method === 'GET' && (res.status === 401 || res.status === 403)) {
      const fallback = maybeFallback(upstreamPath, 'admin_auth_required');
      if (fallback) return fallback;
    }

    const payload = await res.text();
    const response = new NextResponse(payload, { status: res.status });

    const responseContentType = res.headers.get('content-type');
    const responseEtag = res.headers.get('etag');

    if (responseContentType) response.headers.set('content-type', responseContentType);
    if (responseEtag) response.headers.set('ETag', responseEtag);

    return response;
  } catch (error: any) {
    if (method === 'GET') {
      const fallback = maybeFallback(upstreamPath, 'upstream_unavailable');
      if (fallback) return fallback;
    }

    return NextResponse.json(
      { detail: error?.message || 'Admin proxy request failed' },
      { status: 502 },
    );
  }
}

export async function GET(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}

export async function POST(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}

export async function PUT(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}

export async function PATCH(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}

export async function DELETE(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}

export async function OPTIONS(request: NextRequest, ctx: { params: Promise<{ path: string[] }> }) {
  return handleProxy(request, ctx);
}
