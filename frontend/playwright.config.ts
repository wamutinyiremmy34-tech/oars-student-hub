import { defineConfig } from "@playwright/test";
import { API_PORT, WEB_PORT, backendEnv } from "./e2e/env";

export default defineConfig({
  testDir: "./e2e",
  globalSetup: "./e2e/global-setup.ts",
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: { baseURL: `http://localhost:${WEB_PORT}`, trace: "retain-on-failure" },
  webServer: [
    {
      command: `python -m uvicorn app.main:create_app --factory --port ${API_PORT}`,
      cwd: "../backend",
      env: backendEnv(),
      url: `http://localhost:${API_PORT}/health`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
    {
      command: `npm run dev -- --port ${WEB_PORT} --strictPort`,
      env: { VITE_DEV_API_TARGET: `http://localhost:${API_PORT}`, PATH: process.env.PATH ?? "" },
      url: `http://localhost:${WEB_PORT}`,
      reuseExistingServer: !process.env.CI,
      timeout: 60_000,
    },
  ],
});
