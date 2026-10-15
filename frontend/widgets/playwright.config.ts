import { defineConfig, devices } from '@playwright/test';

// Tests run against the built files (npm run build first), served by scripts/serve.mjs.
// Uses the Edge already installed on Windows, so no browser download is needed.
export default defineConfig({
  testDir: 'tests',
  fullyParallel: true,
  use: { baseURL: 'http://localhost:4173', channel: 'msedge' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel: 'msedge' } },
  ],
  webServer: { command: 'node scripts/serve.mjs', url: 'http://localhost:4173/host.html', reuseExistingServer: true },
});
