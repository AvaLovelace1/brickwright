<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Header from "./Header.svelte";
  import { expect } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Header",
    component: Header,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Header has a logo", async () => {
      const logo = canvas.getByRole("img", { name: /logo/i });
      await expect(logo).toBeVisible();
    });
    await step("Header has external button links", async () => {
      for (const name of [/paper/i, /code/i]) {
        const link = canvas.getByRole("link", { name });
        await expect(link).toBeVisible();
        await expect(link).toHaveAttribute("target", "_blank");
        await expect(link).toHaveAttribute("rel", "external noopener");
      }
    });
  }}
/>
