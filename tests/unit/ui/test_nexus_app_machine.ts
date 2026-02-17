import { CAPABILITY_POLL_INTERVAL_MS, CAPABILITY_RETRY_DELAY_MS, CONFIG_POLL_INTERVAL_MS } from '../../../ui_service/src/lib/runtime-params';
import { nexusAppMachine } from '../../../ui_service/src/machines/nexusApp';
import { classifyError, NexusErrorType } from '../../../ui_service/src/lib/errors';
import { createActor } from 'xstate';

function assert(condition: boolean, message: string): void {
  if (!condition) {
    throw new Error(message);
  }
}

// Parametric synchronization guard: machine must remain wired to shared runtime params.
assert(CAPABILITY_POLL_INTERVAL_MS > 0, 'CAPABILITY_POLL_INTERVAL_MS must be positive');
assert(CONFIG_POLL_INTERVAL_MS > 0, 'CONFIG_POLL_INTERVAL_MS must be positive');
assert(CAPABILITY_RETRY_DELAY_MS > 0, 'CAPABILITY_RETRY_DELAY_MS must be positive');

const appActor = createActor(nexusAppMachine);
appActor.start();
const machineInitial = appActor.getSnapshot();
assert(machineInitial.matches({ capability: 'loading' }), 'nexusAppMachine should start in capability.loading');

const authError = classifyError({ status: 401 });
assert(authError === NexusErrorType.NOT_AUTHORIZED, '401 must classify as NOT_AUTHORIZED');

const degradedError = classifyError({ status: 503 });
assert(degradedError === NexusErrorType.DEGRADED_PROVIDER, '503 must classify as DEGRADED_PROVIDER');
