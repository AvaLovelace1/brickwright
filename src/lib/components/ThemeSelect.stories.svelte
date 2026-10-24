<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor } from "storybook/test";
  import ThemeSelect from "./ThemeSelect.svelte";

  const { Story } = defineMeta({
    title: "Components/ThemeSelect",
    component: ThemeSelect,
    tags: ["autodocs"],
  });
</script>

<Story
  name="Select a Theme"
  play={async ({ canvas, userEvent }) => {
    const trigger = canvas.getByRole("combobox", { name: /^Theme / });
    for (const label of ["Dark", "Light", "Auto"]) {
      await userEvent.click(trigger);
      const option = await screen.findByRole("option", { name: label });
      await waitFor(() => expect(option).toBeVisible());
      await userEvent.click(option);
      await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());

      await expect(trigger).toHaveAccessibleName(`Theme ${label}`);
      await expect(trigger).toHaveFocus();
      await expect(localStorage.getItem("brickwright-theme")).toBe(label.toLowerCase());
      await expect(document.documentElement.dataset.theme).toBe(
        label === "Auto" ? undefined : label.toLowerCase(),
      );
    }
  }}
/>
