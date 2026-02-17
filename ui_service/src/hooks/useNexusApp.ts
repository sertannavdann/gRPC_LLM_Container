/**
 * useNexusApp Hook
 *
 * React hook bridging nexusAppMachine to components via @xstate/react useMachine.
 * Provides typed state access and event dispatch for capability polling, data source status, and auth.
 *
 * Registers XState send function with Zustand store on mount for cross-page event bridging
 * (enables chat tool calls to trigger CAPABILITY_REFRESH_REQUESTED events).
 */

import { useEffect } from 'react';
import { useMachine } from '@xstate/react';
import { nexusAppMachine, type NexusErrorType } from '../machines/nexusApp';
import type { CapabilityEnvelope } from '../lib/adminClient';

export interface UseNexusAppReturn {
  // State
  envelope: CapabilityEnvelope | null;
  isLoading: boolean;
  isError: boolean;
  error: NexusErrorType | null;

  // Data source status (parallel region)
  isLive: boolean;
  isMock: boolean;
  isOffline: boolean;
  isUnknown: boolean;

  // Auth status (parallel region)
  isAuthenticated: boolean;

  // Actions
  refresh: () => void;
}

/**
 * Hook providing access to the NEXUS root application state machine.
 *
 * Usage:
 * ```tsx
 * const { envelope, isLoading, isLive, refresh } = useNexusApp();
 *
 * if (isLoading) return <Spinner />;
 * if (!envelope) return <Error />;
 *
 * return (
 *   <div>
 *     <StatusBadge isLive={isLive} />
 *     <ModuleList modules={envelope.modules} />
 *     <Button onClick={refresh}>Refresh</Button>
 *   </div>
 * );
 * ```
 */
export function useNexusApp(): UseNexusAppReturn {
  const [state, send] = useMachine(nexusAppMachine);

  // Register XState send function with Zustand store for cross-page event bridging
  useEffect(() => {
    // Dynamically import to avoid circular dependencies
    import('../stores/nexusStore').then((module) => {
      module.nexusStore.getState().setXStateSend(send);
    });

    return () => {
      // Cleanup on unmount
      import('../stores/nexusStore').then((module) => {
        module.nexusStore.getState().setXStateSend(null);
      });
    };
  }, [send]);

  return {
    // State
    envelope: state.context.envelope,
    isLoading: state.matches({ capability: 'loading' }),
    isError: state.matches({ capability: 'error' }),
    error: state.context.error,

    // Data source status (parallel region — check matches)
    isLive: state.matches({ dataSource: 'live' }),
    isMock: state.matches({ dataSource: 'mock' }),
    isOffline: state.matches({ dataSource: 'offline' }),
    isUnknown: state.matches({ dataSource: 'unknown' }),

    // Auth status (parallel region)
    isAuthenticated: state.matches({ auth: 'authenticated' }),

    // Actions
    refresh: () => send({ type: 'CAPABILITY_REFRESH_REQUESTED' }),
  };
}
