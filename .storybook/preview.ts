import type { Preview, SvelteRenderer } from "@storybook/sveltekit";
import { withThemeByDataAttribute } from "@storybook/addon-themes";

import "@fontsource-variable/source-sans-3/wght.css";
import "@fontsource-variable/source-sans-3/wght-italic.css";
import "@fontsource-variable/rokkitt/wght.css";
import "@fontsource-variable/rokkitt/wght-italic.css";
import "@fontsource-variable/source-code-pro/wght.css";
import "@fontsource-variable/source-code-pro/wght-italic.css";
import "../src/app.css";

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
  decorators: [
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
