import { defineConfig, devices } from "@playwright/test";

const mockApiPort = 8001;
const webPort = 3001;

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 60_000,
  expect: {
    timeout: 10_000,
  },
  fullyParallel: true,
  reporter: "list",
  use: {
    baseURL: `http://127.0.0.1:${webPort}`,
    trace: "on-first-retry",
  },
  webServer: [
    {
      command: `node tests/e2e/mock-api-server.mjs ${mockApiPort}`,
      port: mockApiPort,
      reuseExistingServer: !process.env.CI,
      cwd: ".",
    },
    {
      command: `npm run dev -- --hostname 127.0.0.1 --port ${webPort}`,
      port: webPort,
      reuseExistingServer: !process.env.CI,
      cwd: ".",
      env: {
        NEXT_TELEMETRY_DISABLED: "1",
        TRADE_API_BASE_URL: `http://127.0.0.1:${mockApiPort}`,
      },
    },
  ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
