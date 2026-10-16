<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Button from "./Button.svelte";
  import { expect, fn, userEvent } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Button",
    component: Button,
    tags: ["autodocs"],
  });

  const handleClick = fn();
</script>

<!-- If `action` is a function, clicking the button runs it. -->
<Story
  name="Action Button"
  args={{ text: "Run Action", action: handleClick }}
  play={async ({ canvas, step }) => {
    const button = canvas.getByRole("button", { name: "Run Action" });
    await step("Button renders", async () => {
      await expect(button).toBeVisible();
      await expect(button).toHaveClass("bb-btn");
    });
    await step("Clicking button runs handler", async () => {
      await userEvent.click(button);
      await expect(handleClick).toHaveBeenCalledTimes(1);
    });
  }}
/>

<!-- If `action` is a string, the button becomes a link. -->
<Story
  name="Link Button"
  args={{ text: "Go Home", action: "/" }}
  play={async ({ canvas, step }) => {
    const link = canvas.getByRole("link", { name: "Go Home" });
    await step("Button renders as a link", async () => {
      await expect(link).toBeVisible();
      await expect(link).toHaveClass("bb-btn");
    });
    await step("Link is internal anchor without external attrs", async () => {
      await expect(link).toHaveAttribute("href", "/");
      await expect(link).not.toHaveAttribute("target");
      await expect(link).not.toHaveAttribute("rel");
    });
  }}
/>

<!-- An external link sets `target` and `rel`. -->
<Story
  name="External Link"
  args={{ text: "External Docs", action: "https://example.com/docs" }}
  play={async ({ canvas, step }) => {
    const link = canvas.getByRole("link", { name: "External Docs" });
    await step("Button renders as external anchor with target and rel", async () => {
      await expect(link).toHaveAttribute("href", "https://example.com/docs");
      await expect(link).toHaveAttribute("target", "_blank");
      await expect(link).toHaveAttribute("rel", "external noopener");
    });
  }}
/>

<!-- Buttons can render with an icon included before the label. -->
<Story
  name="Icon Button"
  args={{ text: "Download Report", action: handleClick, icon: "tdesign--download" }}
  play={async ({ canvas, step }) => {
    const button = canvas.getByRole("button", { name: "Download Report" });
    await step("Button renders with an icon", async () => {
      const icon = button.querySelector(".iconify");
      await expect(icon).not.toBeNull();
      await expect(icon).toHaveClass("tdesign--download");
    });
  }}
/>

<!-- Custom classes are merged onto the base button class. -->
<Story
  name="Custom Class Button"
  args={{ text: "Primary Action", action: handleClick, class: "bb-btn-primary" }}
  play={async ({ canvas, step }) => {
    const button = canvas.getByRole("button", { name: "Primary Action" });
    await step("Button applies custom classes", async () => {
      await expect(button).toHaveClass("bb-btn", "bb-btn-primary");
    });
  }}
/>
