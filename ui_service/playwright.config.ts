import { defineConfig, devices } from '@playwright/test';
import { E2E_BASE_URL } from './e2e/util';

/**
 * Playwright configuration for the pipeline SSE E2E suite (REQ-018).
 *
 * Deliberately no dev-server-launcher entry — these tests run against the
 * running docker-compose stack (`make up`), not a Playwright-managed server.
 * `globalSetup` fails fast with a clear message if the stack is down instead
 * of letting individual tests hang on the SSE connection.
 */
export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/global-setup.ts',
  timeout: 60_000,
  expect: {
    timeout: 15_000,
  },
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: E2E_BASE_URL,
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
