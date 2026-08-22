/**
 * NEXUS Pipeline Store (Zustand)
 *
 * SSE transport and node/panel selection moved to `ui_service/src/machines/pipelinePage.ts`
 * (D-14, plan 08-07/08-08) — `pipelinePageMachine`'s `sseConnection` fromCallback actor is
 * now the sole EventSource owner, and its `selection`/`reviewPanel` regions own node
 * selection and the review panel state. This store now covers module admin actions
 * (enable/disable/reload) and the ad-hoc test runner only.
 */
import { create } from 'zustand';
import {
  type ModuleDetail,
  type TestRunResult,
  adminApi,
} from '@/lib/adminClient';

// Kept for NodeDetailPanel.tsx, which imports this type — selection itself now
// lives in pipelinePageMachine's `selection` region (D-14), not this store.
export interface SelectedNode {
  type: string;
  id: string;
  data: Record<string, unknown>;
}

interface NexusStore {
  // Module list (from admin API)
  modules: ModuleDetail[];
  modulesLoading: boolean;

  // Test runner
  testRunning: boolean;
  testResult: TestRunResult | null;

  // Actions
  fetchModules: () => Promise<void>;
  enableModule: (cat: string, plat: string) => Promise<void>;
  disableModule: (cat: string, plat: string) => Promise<void>;
  reloadModule: (cat: string, plat: string) => Promise<void>;
  runModuleTests: (cat: string, plat: string) => Promise<void>;
}

export const useNexusStore = create<NexusStore>((set, get) => ({
  modules: [],
  modulesLoading: false,
  testRunning: false,
  testResult: null,

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

  runModuleTests: async (cat, plat) => {
    set({ testRunning: true, testResult: null });
    try {
      const result = await adminApi.runModuleTests(cat, plat);
      set({ testRunning: false, testResult: result });
    } catch {
      set({ testRunning: false });
    }
  },
}));
