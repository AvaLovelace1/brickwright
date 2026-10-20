import type { StorybookConfig } from "@storybook/sveltekit";

const config: StorybookConfig = {
  stories: ["../src/**/*.stories.@(js|ts|svelte)"],
  addons: [
    "@chromatic-com/storybook",
    "@storybook/addon-a11y",
    "@storybook/addon-docs",
    "@storybook/addon-svelte-csf",
    "@storybook/addon-themes",
    "@storybook/addon-vitest",
  ],
  framework: "@storybook/sveltekit",
  viteFinal: (config, { configType }) => {
    if (configType !== "PRODUCTION") return config;
    // Standalone Storybook frames do not run the SvelteKit 3 bootstrap that supplies this payload.
    return {
      ...config,
      define: { ...config.define, __SVELTEKIT_PAYLOAD__: "undefined" },
    };
  },
};
export default config;
