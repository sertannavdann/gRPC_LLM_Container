/**
 * NEXUS Pipeline Store (Zustand)
 *
 * Central state for the pipeline visualization page.
 * Manages SSE connection, service/module state, and admin actions.
 */
import { create } from 'zustand';
import {
  type PipelineState,
  type ModuleDetail,
  connectPipelineSSE,
  adminApi,
} from '@/lib/adminClient';

interface NexusStore {
  // SSE pipeline state
  pipeline: PipelineState | null;
  connected: boolean;
  lastUpdate: number;

  // Module list (from admin API)
  modules: ModuleDetail[];
  modulesLoading: boolean;

  // Actions
  startSSE: () => void;
  stopSSE: () => void;
  fetchModules: () => Promise<void>;
  enableModule: (cat: string, plat: string) => Promise<void>;
  disableModule: (cat: string, plat: string) => Promise<void>;
  reloadModule: (cat: string, plat: string) => Promise<void>;
}

let _eventSource: EventSource | null = null;

export const useNexusStore = create<NexusStore>((set, get) => ({
  pipeline: null,
  connected: false,
  lastUpdate: 0,
  modules: [],
  modulesLoading: false,

  startSSE: () => {
    if (_eventSource) return;
    _eventSource = connectPipelineSSE(
      (state) => set({ pipeline: state, connected: true, lastUpdate: Date.now() }),
      () => set({ connected: false }),
    );
  },

  stopSSE: () => {
    _eventSource?.close();
    _eventSource = null;
    set({ connected: false });
  },

  fetchModules: async () => {
    set({ modulesLoading: true });
    try {
      const res = await adminApi.listModules();
      set({ modules: res.modules, modulesLoading: false });
    } catch {
      set({ modulesLoading: false });
    }
  },

  enableModule: async (cat, plat) => {
    await adminApi.enableModule(cat, plat);
    get().fetchModules();
  },

  disableModule: async (cat, plat) => {
    await adminApi.disableModule(cat, plat);
    get().fetchModules();
  },

  reloadModule: async (cat, plat) => {
    await adminApi.reloadModule(cat, plat);
    get().fetchModules();
  },
}));
