<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Citation from "./Citation.svelte";
  import { expect } from "storybook/test";

  const { Story } = defineMeta({
    title: "Sections/Citation",
    component: Citation,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Section has the expected elements", async () => {
      const heading = canvas.getByRole("heading", { level: 2 });
      await expect(heading).toBeVisible();
      const paragraph = canvas.queryAllByRole("paragraph")[0];
      await expect(paragraph).toBeVisible();
      const copyButton = canvas.getByRole("button", { name: /copy/i });
      await expect(copyButton).toBeVisible();
    });
  }}
/>
