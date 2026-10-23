<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Slider from "./Slider.svelte";
  import { expect, screen, waitFor, waitForElementToBeRemoved } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Slider",
    component: Slider,
    tags: ["autodocs"],
    args: {
      label: "Slider",
      value: 1,
      min: 1,
      max: 100,
      step: 1,
      fmtValue: (value) => `Value: ${value.toString()}`,
    },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    const sliderHandle = canvas.getByRole("slider");
    await expect(sliderHandle).toHaveAttribute("aria-valuetext", "Value: 1");
    await step("Tooltip is not visible initially", async () => {
      await expect(screen.queryByRole("tooltip")).toBeNull();
    });
    await step("Focusing the handle brings up tooltip", async () => {
      sliderHandle.focus();
      const tooltipContent = await screen.findByRole("tooltip", { name: "Value: 1" });
      await waitFor(() => expect(tooltipContent).toBeVisible());
    });
    await step("Blurring the handle hides tooltip", async () => {
      sliderHandle.blur();
      await waitForElementToBeRemoved(() => screen.queryByRole("tooltip"));
    });
  }}
/>
