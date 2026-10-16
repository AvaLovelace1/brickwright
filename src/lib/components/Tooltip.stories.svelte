<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { Tooltip as BitsTooltip } from "bits-ui";
  import Tooltip from "./Tooltip.svelte";
  import type { Props as TooltipProps } from "./Tooltip.svelte";
  import { expect, waitFor, screen, waitForElementToBeRemoved } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Tooltip",
    component: Tooltip,
    tags: ["autodocs"],
    render: template,
    args: { class: "bb-btn" },
  });

  const BUTTON_NAME = "Hover me";
  const TOOLTIP_TEXT = "Tooltip text";
</script>

{#snippet template(args: TooltipProps)}
  <BitsTooltip.Provider>
    <Tooltip {...args}>
      {BUTTON_NAME}
      {#snippet tooltipContent()}<p>{TOOLTIP_TEXT}</p>{/snippet}
    </Tooltip>
  </BitsTooltip.Provider>
{/snippet}

<!-- Tooltip appears on hover. -->
<Story
  name="Default"
  play={async ({ canvas, userEvent, step }) => {
    await step("Hover to show tooltip", async () => {
      const tooltipTrigger = canvas.getByRole("button", { name: BUTTON_NAME });
      await userEvent.hover(tooltipTrigger);
      const tooltipContent = await screen.findByRole("tooltip");
      await waitFor(() => expect(tooltipContent).toBeVisible());
      await expect(tooltipContent).toHaveTextContent(TOOLTIP_TEXT);
    });
    await step("Unhover to hide tooltip", async () => {
      const tooltipTrigger = canvas.getByRole("button", { name: BUTTON_NAME });
      await userEvent.unhover(tooltipTrigger);
      await waitForElementToBeRemoved(() => screen.queryByRole("tooltip"));
    });
  }}
/>
