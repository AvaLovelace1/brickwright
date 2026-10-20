<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Button from "./Button.svelte";
  import type { ComponentProps } from "svelte";
  import { Tooltip as BitsTooltip } from "bits-ui";
  import { expect, fn, screen, userEvent, waitFor } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Button",
    component: Button,
    tags: ["autodocs"],
    render: template,
  });

  const handleClick = fn();
  const handleIconClick = fn();
  const handleDisabledClick = fn();
</script>

{#snippet template(args: ComponentProps<typeof Button>)}
  <BitsTooltip.Provider delayDuration={0}>
    <Button {...args} />
  </BitsTooltip.Provider>
{/snippet}

<Story
  name="Action Button"
  args={{ text: "Run Action", action: handleClick }}
  play={async ({ canvas, step }) => {
    const button = canvas.getByRole("button", { name: "Run Action" });
    await step("Button renders", async () => {
      await expect(button).toBeVisible();
    });
    await step("Clicking button runs handler", async () => {
      await userEvent.click(button);
      await expect(handleClick).toHaveBeenCalledTimes(1);
    });
  }}
/>

<Story
  name="Icon Only"
  args={{
    text: "Next step",
    action: handleIconClick,
    icon: "tdesign--chevron-right",
    iconOnly: true,
  }}
  play={async ({ canvas, userEvent }) => {
    const button = canvas.getByRole("button", { name: "Next step" });
    await expect(button).toHaveAttribute("type", "button");
    await userEvent.hover(button);
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(screen.getByRole("tooltip")).toHaveTextContent("Next step");
    await userEvent.unhover(button);
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    button.focus();
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(button).toHaveAccessibleDescription("Next step");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    await userEvent.keyboard("{Enter} ");
    await expect(handleIconClick).toHaveBeenCalledTimes(2);
  }}
/>

<Story
  name="Disabled Action"
  args={{ text: "Previous step", action: handleDisabledClick, disabled: true }}
  play={async ({ canvas }) => {
    const button = canvas.getByRole("button", { name: "Previous step" }) as HTMLButtonElement;
    await expect(button).toBeDisabled();
    button.click();
    await expect(handleDisabledClick).not.toHaveBeenCalled();
  }}
/>

<Story
  name="Link Button"
  args={{ text: "Go Home", action: "/" }}
  play={async ({ canvas, step }) => {
    const link = canvas.getByRole("link", { name: "Go Home" });
    await step("Button renders as a link", async () => {
      await expect(link).toBeVisible();
    });
    await step("Link is internal anchor without external attrs", async () => {
      await expect(link).toHaveAttribute("href", "/");
      await expect(link).not.toHaveAttribute("target");
      await expect(link).not.toHaveAttribute("rel");
    });
  }}
/>

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

<Story
  name="Icon Only Link"
  args={{
    text: "Source code",
    action: "https://example.com/source",
    icon: "tdesign--logo-github",
    iconOnly: true,
  }}
  play={async ({ canvas, userEvent }) => {
    const link = canvas.getByRole("link", { name: "Source code" });
    await expect(link).toHaveAttribute("href", "https://example.com/source");
    await expect(link).toHaveAttribute("target", "_blank");
    await expect(link).toHaveAttribute("rel", "external noopener");
    await userEvent.hover(link);
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(screen.getByRole("tooltip")).toHaveTextContent("Source code");
    await userEvent.unhover(link);
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  }}
/>
