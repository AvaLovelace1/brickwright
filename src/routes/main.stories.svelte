<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Page from "./+page.svelte";
  import { expect } from "storybook/test";
  import { Tooltip as BitsTooltip } from "bits-ui";

  const { Story } = defineMeta({
    title: "Pages/Main Page",
    component: Page,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <BitsTooltip.Provider><Page /></BitsTooltip.Provider>
{/snippet}

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Page has a styled heading", async () => {
      const heading = canvas.getByRole("heading", { level: 1 });
      await expect(heading).toBeVisible();
      const headingStyle = window.getComputedStyle(heading);
      await expect(headingStyle.fontFamily).toContain("Rokkitt");
    });
    await step("Page has a styled paragraph", async () => {
      const paragraph = canvas.queryAllByRole("paragraph")[0];
      await expect(paragraph).toBeVisible();
      const paragraphStyle = window.getComputedStyle(paragraph);
      await expect(paragraphStyle.fontFamily).toContain("Source Sans");
    });
  }}
/>
