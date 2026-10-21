import { defineConfig, devices } from '@playwright/test';

// Tests run against the built files (npm run build first), served by scripts/serve.mjs.
// Uses the Edge already installed on Windows, so no browser download is needed.
export default defineConfig({
  testDir: 'tests',
  fullyParallel: true,
  // A failed test runs once more with a full trace: a rare timing failure shows as 'flaky' with a
  // trace to inspect (npx playwright show-trace), while a real bug still fails twice.
  retries: 1,
  use: { baseURL: 'http://localhost:4173', channel: 'msedge', trace: 'on-first-retry' },
  projects: [
    { name: 'desktop', use: { ...devices['Desktop Edge'], channel: 'msedge' } },
    { name: 'mobile', use: { ...devices['Pixel 7'], channel: 'msedge' } },
    // iPhone screen size in Edge (Safari is not installed); only the screen-sensitive tests.
    {
      name: 'iphone',
      use: { ...devices['iPhone 13'], browserName: 'chromium', channel: 'msedge' },
      testMatch: /(panel|composer|menu|chips|booking)\.spec\.ts/,
    },
  ],
  webServer: {
    command: 'node scripts/serve.mjs',
    url: 'http://localhost:4173/host.html',
    reuseExistingServer: true,
  },
});
