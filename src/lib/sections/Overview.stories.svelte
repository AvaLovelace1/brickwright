<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import Overview from "./Overview.svelte";

  const { Story } = defineMeta({
    title: "Sections/Overview",
    component: Overview,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Author names link to their homepages", async () => {
      const author = canvas.getByRole("link", { name: "Ava\u00A0Pun" });
      await expect(author).toHaveAttribute("href", expect.stringMatching(/^https:\/\//));
      await expect(author).toHaveAttribute("target", "_blank");
      await expect(author).toHaveAttribute("rel", "external noopener");
    });
  }}
/>
