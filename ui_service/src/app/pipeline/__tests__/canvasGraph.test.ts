import { describe, it, expect } from 'vitest';
import { buildCanvasGraph, STAGE_NODES, STAGE_EDGES } from '../canvasGraph';
import { STAGE_NODE_IDS } from '@/machines/pipelinePage';
import type { PipelineState } from '@/lib/adminClient';

function fixturePipeline(): PipelineState {
  return {
    services: {
      orchestrator: { name: 'orchestrator', state: 'running', latency_ms: 12 },
    },
    modules: [
      { id: 'test/hello', name: 'hello', state: 'running', category: 'test', status: 'installed', pending_approval: false },
      { id: 'e2e_probe/probe', name: 'probe', state: 'disabled', category: 'e2e_probe', status: 'pending', pending_approval: true },
    ],
    adapters: [
      {
        id: 'weather/openweather',
        name: 'openweather',
        category: 'weather',
        platform: 'openweather',
        state: 'running',
        requires_auth: true,
        has_credentials: true,
      },
    ],
    adapters_count: 1,
    tools: [
      { name: 'weather_check', stage: 'tools', connected_adapters: ['weather/openweather'] },
    ],
    stage_tools: { tools: ['weather_check'] },
    timestamp: 1700000000,
  };
}

describe('buildCanvasGraph', () => {
  it('null pipeline yields exactly the four stage nodes and three stage edges', () => {
    const { nodes, edges } = buildCanvasGraph(null);
    expect(nodes).toHaveLength(4);
    expect(nodes.map((n) => n.id).sort()).toEqual([...STAGE_NODE_IDS].sort());
    expect(edges).toHaveLength(3);
    expect(nodes).toEqual(STAGE_NODES);
    expect(edges).toEqual(STAGE_EDGES);
  });

  it('a fixture pipeline yields the expected node ids with no duplicate ids', () => {
    const { nodes } = buildCanvasGraph(fixturePipeline());
    const ids = nodes.map((n) => n.id);
    expect(new Set(ids).size).toBe(ids.length);
    expect(ids).toContain('svc-orchestrator');
    expect(ids).toContain('tool-weather_check');
    expect(ids).toContain('adapter-weather/openweather');
    expect(ids).toContain('module-test/hello');
    expect(ids).toContain('module-e2e_probe/probe');
  });

  it('pending-approval modules sort leftmost (lower x than non-pending ones)', () => {
    const { nodes } = buildCanvasGraph(fixturePipeline());
    const pending = nodes.find((n) => n.id === 'module-e2e_probe/probe')!;
    const nonPending = nodes.find((n) => n.id === 'module-test/hello')!;
    expect(pending.position.x).toBeLessThan(nonPending.position.x);
  });

  it('a supplied positions entry overrides the computed layout for that id while others keep their computed values', () => {
    const pipeline = fixturePipeline();
    const { nodes: computedNodes } = buildCanvasGraph(pipeline);
    const computedSvc = computedNodes.find((n) => n.id === 'svc-orchestrator')!;
    const override = new Map([['svc-orchestrator', { x: 999, y: 888 }]]);
    const { nodes } = buildCanvasGraph(pipeline, override);
    const svc = nodes.find((n) => n.id === 'svc-orchestrator')!;
    expect(svc.position).toEqual({ x: 999, y: 888 });
    const tool = nodes.find((n) => n.id === 'tool-weather_check')!;
    const computedTool = computedNodes.find((n) => n.id === 'tool-weather_check')!;
    expect(tool.position).toEqual(computedTool.position);
  });

  it('layout contains an entry for every returned node id', () => {
    const { nodes, layout } = buildCanvasGraph(fixturePipeline());
    for (const n of nodes) {
      expect(layout.has(n.id)).toBe(true);
    }
  });
});
