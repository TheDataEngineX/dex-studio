import { defineConfig } from "@playwright/test";
export default defineConfig({
  testMatch: "*.spec.ts",
  fullyParallel: true,
  retries: 1,
  reporter: [["html", { outputFolder: "playwright-report" }]],
  use: {
    baseURL: "http://127.0.0.1:7860",
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "setup",
      testMatch: "seed.spec.ts",
    },
    {
      name: "chromium",
      testMatch: "tests-e2e/**/*.spec.ts",
      dependencies: ["setup"],
      use: {
        storageState: ".playwright/auth.json",
      },
    },
  ],
});
