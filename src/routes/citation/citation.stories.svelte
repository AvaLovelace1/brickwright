<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Page from "./+page.svelte";
  import { expect } from "storybook/test";

  const { Story } = defineMeta({
    title: "Pages/Citation Page",
    component: Page,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Page has the expected elements", async () => {
      const heading = canvas.getByRole("heading", { level: 1 });
      await expect(heading).toBeVisible();
      const paragraph = canvas.queryAllByRole("paragraph")[0];
      await expect(paragraph).toBeVisible();
      const copyButton = canvas.getByRole("button", { name: /copy/i });
      await expect(copyButton).toBeVisible();
    });
  }}
/>
