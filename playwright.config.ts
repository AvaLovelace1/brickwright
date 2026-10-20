import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT ?? 4173);
const browsers = [
  { name: "chromium", device: "Desktop Chrome", permissions: ["clipboard-read"] },
  { name: "safari", device: "Desktop Safari", permissions: ["clipboard-read"] },
  { name: "firefox", device: "Desktop Firefox", permissions: [] },
];

export default defineConfig({
  webServer: {
    command: `npm run build && npm run preview -- --port ${port} --strictPort`,
    port,
  },
  testMatch: "**/*.e2e.{ts,js}",
  use: { baseURL: `http://localhost:${port}` },
  reporter: "html",
  projects: (["light", "dark"] as const).flatMap((colorScheme) =>
    browsers.map(({ name, device, permissions }) => ({
      name: `${name}-${colorScheme}`,
      use: { ...devices[device], colorScheme, permissions },
    })),
  ),
});
