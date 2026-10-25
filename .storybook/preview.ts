import type { Preview, SvelteRenderer } from "@storybook/sveltekit";
import { withThemeByDataAttribute } from "@storybook/addon-themes";
import { Tooltip } from "bits-ui";
import { configure } from "storybook/test";
import SharedCanvas from "../src/lib/components/SharedCanvas.svelte";

import "../src/app.css";

// Transitions and async updates can take over a second while other tests share the machine.
configure({ asyncUtilTimeout: 5_000 });

const preview: Preview = {
  parameters: {
    backgrounds: {
      options: {
        base: { name: "Base", value: "var(--color-bg)" },
      },
    },
    controls: {
      matchers: {
        color: /(background|color)$/i,
        date: /Date$/i,
      },
    },
    a11y: { test: "error" },
  },
  initialGlobals: {
    backgrounds: { value: "base" },
  },
  // Stories that change the theme leave the saved preference and the page theme as they found them.
  beforeEach() {
    const saved = localStorage.getItem("brickwright-theme");
    const theme = document.documentElement.dataset.theme;
    return () => {
      if (saved === null) localStorage.removeItem("brickwright-theme");
      else localStorage.setItem("brickwright-theme", saved);
      if (theme === undefined) delete document.documentElement.dataset.theme;
      else document.documentElement.dataset.theme = theme;
    };
  },
  decorators: [
    () => ({ Component: Tooltip.Provider }),
    () => ({ Component: SharedCanvas }),
    withThemeByDataAttribute<SvelteRenderer>({
      themes: {
        light: "light",
        dark: "dark",
      },
      defaultTheme: "light",
      attributeName: "data-theme",
    }),
  ],
};

export default preview;
