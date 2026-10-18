import { defineConfig, devices } from "@playwright/test";

export default defineConfig({
  webServer: { command: "npm run build && npm run preview", port: 4173 },
  testMatch: "**/*.e2e.{ts,js}",
  use: { baseURL: "http://localhost:4173" },
  reporter: "html",
  projects: [
    {
      name: "chromium-light",
      use: { ...devices["Desktop Chrome"], colorScheme: "light", permissions: ["clipboard-read"] },
    },
    {
      name: "safari-light",
      use: { ...devices["Desktop Safari"], colorScheme: "light", permissions: ["clipboard-read"] },
    },
    {
      name: "firefox-light",
      use: { ...devices["Desktop Firefox"], colorScheme: "light" },
    },
    {
      name: "chromium-dark",
      use: { ...devices["Desktop Chrome"], colorScheme: "dark", permissions: ["clipboard-read"] },
    },
    {
      name: "safari-dark",
      use: { ...devices["Desktop Safari"], colorScheme: "dark", permissions: ["clipboard-read"] },
    },
    {
      name: "firefox-dark",
      use: { ...devices["Desktop Firefox"], colorScheme: "dark" },
    },
  ],
});
