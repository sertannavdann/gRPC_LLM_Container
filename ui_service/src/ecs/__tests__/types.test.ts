import { describe, it, expect } from 'vitest';
import { KINDS, STATUSES, entityIdFor } from '../types';

describe('entityIdFor', () => {
  it('produces the react-flow service node id scheme', () => {
    expect(entityIdFor('service', 'orchestrator')).toBe('svc-orchestrator');
  });

  it('produces the react-flow module node id scheme, preserving slashes in the key', () => {
    expect(entityIdFor('module', 'weather/openweather')).toBe(
      'module-weather/openweather'
    );
  });

  it('produces the react-flow adapter/tool/stage node id schemes', () => {
    expect(entityIdFor('adapter', 'cibc')).toBe('adapter-cibc');
    expect(entityIdFor('tool', 'search_knowledge')).toBe('tool-search_knowledge');
    expect(entityIdFor('stage', 'intent')).toBe('stage-intent');
  });
});

describe('KINDS', () => {
  it('is sorted ascending (the verbalizer relies on kind ordering)', () => {
    const sorted = [...KINDS].sort();
    expect([...KINDS]).toEqual(sorted);
  });
});

describe('STATUSES', () => {
  it('contains every state value the production PipelineState unions can produce', () => {
    // ServiceState.state: 'running' | 'error' | 'idle'
    // ModuleState.state: 'running' | 'disabled' | 'failed'
    // AdapterState.state: 'running' | 'error' | 'disabled'
    const productionStates = [
      'running',
      'error',
      'idle',
      'disabled',
      'failed',
    ] as const;

    for (const state of productionStates) {
      expect(STATUSES).toContain(state);
    }
  });
});
