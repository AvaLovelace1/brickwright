import { defineConfig } from "vitest/config";
import path from "node:path";
import adapter from "@sveltejs/adapter-static";
import { enhancedImages } from "@sveltejs/enhanced-img";
import { sveltekit } from "@sveltejs/kit/vite";
import tailwindcss from "@tailwindcss/vite";
import { storybookTest } from "@storybook/addon-vitest/vitest-plugin";
import { playwright } from "@vitest/browser-playwright";

export default defineConfig({
  // Pre-bundles the lazily loaded viewer's dependencies, so Vite never reloads a page
  // mid-interaction to optimize them.
  optimizeDeps: {
    include: [
      "@threlte/core",
      "@threlte/extras",
      "three",
      "three/addons/loaders/HDRLoader.js",
      "three/addons/loaders/LDrawLoader.js",
      "three/addons/materials/LDrawConditionalLineMaterial.js",
    ],
  },
  plugins: [
    tailwindcss(),
    enhancedImages(),
    sveltekit({
      compilerOptions: {
        // Force runes mode for the project, except for libraries. Can be removed in svelte 6.
        runes: ({ filename }) =>
          filename.split(/[/\\]/).includes("node_modules") ? undefined : true,
      },
      adapter: adapter(),
      paths: {
        base: (process.env.BASE_PATH ?? "") as "" | `/${string}`,
        relative: false,
      },
    }),
  ],
  test: {
    expect: {
      requireAssertions: true,
    },
    projects: [
      {
        extends: true,
        test: {
          name: "server",
          environment: "node",
          include: ["src/**/*.{test,spec}.{js,ts}"],
          exclude: ["src/**/*.svelte.{test,spec}.{js,ts}"],
        },
      },
      {
        extends: true,
        plugins: [
          storybookTest({
            configDir: path.join(import.meta.dirname, ".storybook"),
          }),
        ],
        test: {
          name: "storybook",
          testTimeout: 60_000,
          browser: {
            enabled: true,
            headless: true,
            // Full Chromium's headless mode supports hardware WebGL rendering.
            provider: playwright({
              launchOptions: { channel: "chromium" },
              contextOptions: { permissions: ["clipboard-read", "clipboard-write"] },
            }),
            instances: [{ browser: "chromium" }],
          },
        },
      },
    ],
  },
});
