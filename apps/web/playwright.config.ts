import { defineConfig, devices } from "@playwright/test";

const MOCK_API_PORT = 8099;
export const E2E_API_TOKEN = "jeton-e2e-non-secret";

export default defineConfig({
  testDir: "tests/e2e",
  fullyParallel: false,
  forbidOnly: !!process.env.CI,
  retries: 0,
  reporter: [["list"]],
  use: { baseURL: "http://127.0.0.1:3099", trace: "off" },
  projects: [{ name: "chromium-mobile", use: { ...devices["Pixel 7"] } }, { name: "chromium", use: { ...devices["Desktop Chrome"] } }],
  webServer: [
    {
      command: `node tests/e2e/mock-api.mjs`,
      url: `http://127.0.0.1:${MOCK_API_PORT}/__last`,
      env: { MOCK_API_PORT: String(MOCK_API_PORT) },
      reuseExistingServer: false,
    },
    {
      command: "npm run start -- -p 3099 -H 127.0.0.1",
      url: "http://127.0.0.1:3099",
      env: { AVX_API_URL: `http://127.0.0.1:${MOCK_API_PORT}`, AVX_API_TOKEN: E2E_API_TOKEN },
      reuseExistingServer: false,
    },
  ],
});
