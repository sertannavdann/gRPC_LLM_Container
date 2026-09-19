import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// adminClient computes ADMIN_BASE at module load from `typeof window`, so the
// browser branch is exercised by stubbing `window` before a fresh dynamic import.
// (jsdom is not installed; vitest runs in the node environment.)

describe('adminClient browser base', () => {
  beforeEach(() => {
    vi.resetModules();
    vi.stubGlobal('window', {
      location: { protocol: 'http:', hostname: 'localhost' },
    });
    vi.stubGlobal(
      'fetch',
      vi.fn(async () =>
        new Response(JSON.stringify({ status: 'ok', modules_loaded: 0 }), {
          status: 200,
          headers: { 'Content-Type': 'application/json' },
        }),
      ),
    );
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it('routes admin calls through the same-origin proxy without doubling /admin', async () => {
    const { adminApi } = await import('@/lib/adminClient');

    const result = await adminApi.health();
    expect(result.status).toBe('ok');

    const fetchMock = globalThis.fetch as unknown as ReturnType<typeof vi.fn>;
    expect(fetchMock).toHaveBeenCalledTimes(1);

    const url = String(fetchMock.mock.calls[0][0]);
    expect(url.startsWith('/api/admin/health')).toBe(true);
    expect(url).not.toContain('/api/admin/admin');
  });
});
