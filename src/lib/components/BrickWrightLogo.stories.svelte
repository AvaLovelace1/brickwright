<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import BrickWrightLogo from "./BrickWrightLogo.svelte";
  import { expect } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/BrickWright Logo",
    component: BrickWrightLogo,
    tags: ["autodocs"],
    args: { class: "text-4xl" },
  });
</script>

<!-- The BrickWright wordmark. -->
<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Logo image and words are present", async () => {
      const logo = canvas.getByRole("img", { name: /brickwright logo/i });
      const words = canvas.getByText("BrickWright");

      await expect(logo).toBeVisible();
      await expect(words).toBeVisible();
    });
  }}
/>

<!-- Layer variant uses the BrickLayer mark and wordmark. -->
<Story
  name="Layer"
  args={{ variant: "layer" }}
  play={async ({ canvas, step }) => {
    await step("Layer logo image and words are present", async () => {
      const logo = canvas.getByRole("img", { name: /bricklayer logo/i });
      const words = canvas.getByText("BrickLayer");

      await expect(logo).toBeVisible();
      await expect(words).toBeVisible();
    });
  }}
/>

<!-- Agent variant uses the BrickAgent mark and wordmark. -->
<Story
  name="Agent"
  args={{ variant: "agent" }}
  play={async ({ canvas, step }) => {
    await step("Agent logo image and words are present", async () => {
      const logo = canvas.getByRole("img", { name: /brickagent logo/i });
      const words = canvas.getByText("BrickAgent");

      await expect(logo).toBeVisible();
      await expect(words).toBeVisible();
    });
  }}
/>

<!-- You can apply a custom class to the words. -->
<Story
  name="Custom Word Class"
  args={{ textClass: "sr-only" }}
  play={async ({ canvas }) => {
    await expect(canvas.getByText("BrickWright")).toHaveClass("sr-only");
  }}
/>
