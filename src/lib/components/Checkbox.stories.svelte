<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import Checkbox from "./Checkbox.svelte";

  const { Story } = defineMeta({
    title: "Components/Checkbox",
    component: Checkbox,
    tags: ["autodocs"],
    args: { label: "Show intersections" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, userEvent }) => {
    const checkbox = canvas.getByRole("checkbox", { name: "Show intersections" });
    await expect(checkbox).not.toBeChecked();
    await userEvent.click(canvas.getByText("Show intersections"));
    await expect(checkbox).toBeChecked();
    checkbox.focus();
    await userEvent.keyboard(" ");
    await expect(checkbox).not.toBeChecked();
  }}
/>

<Story
  name="Checked"
  args={{ checked: true }}
  play={async ({ canvas, userEvent }) => {
    const checkbox = canvas.getByRole("checkbox", { name: "Show intersections" });
    await expect(checkbox).toBeChecked();
    await userEvent.click(checkbox);
    await expect(checkbox).not.toBeChecked();
  }}
/>

<Story
  name="Disabled"
  args={{ checked: true, disabled: true }}
  play={async ({ canvas, userEvent }) => {
    const checkbox = canvas.getByRole("checkbox", { name: "Show intersections" });
    await expect(checkbox).toBeDisabled();
    await userEvent.click(canvas.getByText("Show intersections"));
    await expect(checkbox).toBeChecked();
  }}
/>
