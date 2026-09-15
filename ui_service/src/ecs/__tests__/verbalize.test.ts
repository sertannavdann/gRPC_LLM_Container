import { describe, it, expect } from 'vitest';
import { createPipelineWorld } from '../world';
import { toCompactDsl } from '../verbalize';
import type { EntityRecord } from '../types';

// Deterministic ~20-entity fixture spanning all five kinds, adapted from
// .planning/spikes/007-llm-writes-world/fixture.mjs to the plan-01
// EntityRecord shape (adapter/module/service/stage/tool + creds/flags/lifecycle).
function makeFixture(): EntityRecord[] {
  const services: EntityRecord[] = [
    { id: 'svc-orchestrator', label: 'Orchestrator', kind: 'service', status: 'running', lifecycle: null, detail: null, latency: 12.4, creds: [], flags: [], x: 120, y: 80 },
    { id: 'svc-llm', label: 'LLM Service', kind: 'service', status: 'running', lifecycle: null, detail: null, latency: 78.6, creds: [], flags: [], x: 320, y: 80 },
    { id: 'svc-dashboard', label: 'Dashboard', kind: 'service', status: 'running', lifecycle: null, detail: null, latency: 3.2, creds: [], flags: [], x: 520, y: 80 },
    { id: 'svc-chroma', label: 'ChromaDB', kind: 'service', status: 'degraded', lifecycle: null, detail: 'reindexing', latency: 22.9, creds: [], flags: [], x: 120, y: 220 },
    { id: 'svc-bridge', label: 'Bridge Service', kind: 'service', status: 'running', lifecycle: null, detail: null, latency: 1.1, creds: [], flags: [], x: 320, y: 220 },
  ];
  const modules: EntityRecord[] = [
    { id: 'module-weather-openweather', label: 'OpenWeather Adapter', kind: 'module', status: 'running', lifecycle: 'enabled', detail: null, latency: null, creds: ['OPENWEATHER_API_KEY'], flags: [], x: 120, y: 380 },
    { id: 'module-calendar-google', label: 'Google Calendar Adapter', kind: 'module', status: 'running', lifecycle: 'enabled', detail: null, latency: null, creds: ['GOOGLE_OAUTH_TOKEN', 'GOOGLE_REFRESH_TOKEN'], flags: [], x: 270, y: 380 },
    { id: 'module-gaming-clashroyale', label: 'Clash Royale Adapter', kind: 'module', status: 'degraded', lifecycle: 'enabled', detail: 'rate limited', latency: 340, creds: ['CLASH_BEARER_TOKEN'], flags: ['retry'], x: 420, y: 380 },
    { id: 'module-finance-cibc', label: 'CIBC CSV Adapter', kind: 'module', status: 'running', lifecycle: 'enabled', detail: null, latency: null, creds: [], flags: [], x: 570, y: 380 },
    { id: 'module-test-hello', label: 'Hello Smoke Test', kind: 'module', status: 'stopped', lifecycle: 'disabled', detail: null, latency: null, creds: [], flags: [], x: 120, y: 500 },
  ];
  const adapters: EntityRecord[] = [
    { id: 'adapter-knowledge-search', label: 'Knowledge Search', kind: 'adapter', status: 'running', lifecycle: null, detail: null, latency: 5.6, creds: ['CHROMA_HOST'], flags: [], x: 120, y: 600 },
    { id: 'adapter-context-bridge', label: 'Context Bridge', kind: 'adapter', status: 'running', lifecycle: null, detail: null, latency: 2.3, creds: [], flags: [], x: 270, y: 600 },
    { id: 'adapter-notion-notes', label: 'Notion Notes Adapter', kind: 'adapter', status: 'building', lifecycle: 'installed', detail: 'compiling', latency: null, creds: ['NOTION_API_KEY'], flags: [], x: 420, y: 600 },
    { id: 'adapter-spotify-music', label: 'Spotify Adapter', kind: 'adapter', status: 'validating', lifecycle: 'installed', detail: null, latency: null, creds: ['SPOTIFY_CLIENT_ID', 'SPOTIFY_CLIENT_SECRET'], flags: [], x: 570, y: 600 },
  ];
  const stages: EntityRecord[] = [
    { id: 'stage-build', label: 'Build', kind: 'stage', status: 'running', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 120, y: 740 },
    { id: 'stage-validate', label: 'Validate', kind: 'stage', status: 'running', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 320, y: 740 },
    { id: 'stage-install', label: 'Install', kind: 'stage', status: 'idle', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 520, y: 740 },
    { id: 'stage-approve', label: 'Approval Gate', kind: 'stage', status: 'idle', lifecycle: null, detail: null, latency: null, creds: [], flags: ['manual'], x: 720, y: 740 },
  ];
  const tools: EntityRecord[] = [
    { id: 'tool-build-module', label: 'Build Module Tool', kind: 'tool', status: 'available', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 120, y: 860 },
    { id: 'tool-validate-module', label: 'Validate Module Tool', kind: 'tool', status: 'available', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 270, y: 860 },
    { id: 'tool-install-module', label: 'Install Module Tool', kind: 'tool', status: 'available', lifecycle: null, detail: null, latency: null, creds: [], flags: [], x: 420, y: 860 },
  ];
  return [...services, ...modules, ...adapters, ...stages, ...tools];
}

describe('verbalize: canonical text stability under churn', () => {
  it('is byte-stable across insertion-order permutations', () => {
    const fixture = makeFixture();
    const worldA = createPipelineWorld();
    const worldB = createPipelineWorld();

    for (const rec of fixture) worldA.add(rec);
    for (const rec of [...fixture].reverse()) worldB.add(rec);

    expect(toCompactDsl(worldA.views())).toBe(toCompactDsl(worldB.views()));
  });

  it('is byte-stable across remove/re-add churn', () => {
    const fixture = makeFixture();
    const world = createPipelineWorld();
    for (const rec of fixture) world.add(rec);

    const before = toCompactDsl(world.views());

    const churnIds = ['module-test-hello', 'svc-bridge', 'tool-install-module'];
    const churnRecs = fixture.filter((r) => churnIds.includes(r.id));
    for (const id of churnIds) world.removeById(id);
    for (const rec of churnRecs) world.add(rec);

    expect(toCompactDsl(world.views())).toBe(before);
  });

  it('renders group headers and entity ids in ascending order', () => {
    const world = createPipelineWorld();
    for (const rec of makeFixture()) world.add(rec);

    const text = toCompactDsl(world.views());
    const groupHeaders = [...text.matchAll(/^\[(\w+)\]$/gm)].map((m) => m[1]);
    expect(groupHeaders).toEqual([...groupHeaders].sort());
    expect(groupHeaders).toEqual(['adapter', 'module', 'service', 'stage', 'tool']);

    const lines = text.split('\n');
    for (const kind of groupHeaders) {
      const startIdx = lines.indexOf(`[${kind}]`);
      const ids: string[] = [];
      for (let i = startIdx + 1; i < lines.length && !lines[i].startsWith('['); i++) {
        const match = lines[i].match(/^(\S+)/);
        if (match) ids.push(match[1]);
      }
      expect(ids).toEqual([...ids].sort());
    }
  });

  it('omits optional segments when null/empty', () => {
    const world = createPipelineWorld();
    world.add({
      id: 'svc-bare',
      label: 'Bare Service',
      kind: 'service',
      status: 'running',
      lifecycle: null,
      detail: null,
      latency: null,
      creds: [],
      flags: [],
      x: 0,
      y: 0,
    });

    const text = toCompactDsl(world.views());
    const line = text.split('\n').find((l) => l.startsWith('svc-bare'))!;
    expect(line).toBe('svc-bare "Bare Service" running');
    expect(line).not.toContain('detail=');
    expect(line).not.toContain('latency=');
    expect(line).not.toContain('creds:');
    expect(line).not.toContain('flags:');
  });

  it('does not change c_state when only position (x/y) is dragged', () => {
    const world = createPipelineWorld();
    for (const rec of makeFixture()) world.add(rec);

    const before = toCompactDsl(world.views());
    world.mutate('svc-orchestrator', { x: 999, y: 999 });
    const after = toCompactDsl(world.views());

    expect(after).toBe(before);
  });
});
