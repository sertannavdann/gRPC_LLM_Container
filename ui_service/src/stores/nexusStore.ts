/**
 * NEXUS Zustand Store
 *
 * Bridges imperative triggers (chat tool calls, API responses) into XState event dispatch.
 * Enables cross-page communication without prop drilling.
 *
 * The XState send function is registered by useNexusApp hook on mount.
 * Chat tool calls can trigger capability refreshes via store.triggerCapabilityRefresh().
 */

import { create } from 'zustand';

export interface NexusStore {
  // XState bridge
  xstateSend: ((event: any) => void) | null;
  setXStateSend: (send: ((event: any) => void) | null) => void;

  // Imperative triggers
  triggerCapabilityRefresh: () => void;
  triggerAuthExpired: () => void;
}

export const nexusStore = create<NexusStore>((set, get) => ({
  // XState bridge (set by useNexusApp hook)
  xstateSend: null,

  setXStateSend: (send) => {
    set({ xstateSend: send });
  },

  // Imperative trigger: Refresh capability envelope
  triggerCapabilityRefresh: () => {
    const { xstateSend } = get();
    if (xstateSend) {
      xstateSend({ type: 'CAPABILITY_REFRESH_REQUESTED' });
    } else {
      console.warn('[nexusStore] xstateSend not registered — capability refresh ignored');
    }
  },

  // Imperative trigger: Auth expired (e.g., from 401 response interceptor)
  triggerAuthExpired: () => {
    const { xstateSend } = get();
    if (xstateSend) {
      xstateSend({ type: 'AUTH_EXPIRED' });
    } else {
      console.warn('[nexusStore] xstateSend not registered — auth expired ignored');
    }
  },
}));

/**
 * Example usage from chat tool call:
 *
 * ```tsx
 * import { nexusStore } from '@/stores/nexusStore';
 *
 * // In chat message handler
 * if (toolCall.name === 'install_module') {
 *   await installModule(toolCall.args);
 *   nexusStore.getState().triggerCapabilityRefresh(); // Trigger XState refresh
 * }
 * ```
 */
