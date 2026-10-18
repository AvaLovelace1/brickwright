<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import RadioGroup from "./RadioGroup.svelte";

  const { Story } = defineMeta({
    title: "Components/RadioGroup",
    component: RadioGroup,
    tags: ["autodocs"],
    args: {
      label: "Model view",
      value: "normal",
      options: [
        { value: "normal", label: "Normal" },
        { value: "invalid", label: "Invalid placements" },
        { value: "intersections", label: "Intersections" },
      ],
    },
  });
</script>

<Story
  name="Select a view"
  play={async ({ canvas, userEvent }) => {
    const normal = canvas.getByRole("radio", { name: "Normal" });
    const invalid = canvas.getByRole("radio", { name: "Invalid placements" });
    await expect(canvas.getByRole("radiogroup", { name: "Model view" })).toBeVisible();
    await expect(normal).toBeChecked();
    await userEvent.click(invalid);
    await expect(invalid).toBeChecked();
    await expect(normal).not.toBeChecked();
    await userEvent.click(invalid);
    await expect(invalid).toBeChecked();
    await userEvent.keyboard("{ArrowRight}");
    await expect(canvas.getByRole("radio", { name: "Intersections" })).toBeChecked();
  }}
/>

<Story
  name="Disabled"
  args={{ disabled: true }}
  play={async ({ canvas }) => {
    for (const radio of canvas.getAllByRole("radio")) await expect(radio).toBeDisabled();
  }}
/>
