import { defineConfig, devices } from "@playwright/test";

const port = Number(process.env.PLAYWRIGHT_PORT ?? 4173);
const browsers = [
  { name: "chromium", device: "Desktop Chrome", channel: "chromium" },
  { name: "safari", device: "Desktop Safari" },
  { name: "firefox", device: "Desktop Firefox" },
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
    browsers.map(({ name, device, ...options }) => ({
      name: `${name}-${colorScheme}`,
      use: { ...devices[device], colorScheme, ...options },
      ...(colorScheme === "dark" && { grep: /@a11y/ }),
    })),
  ),
});
