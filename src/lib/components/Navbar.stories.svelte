<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Navbar from "./Navbar.svelte";
  import { expect, within } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Navbar",
    component: Navbar,
    tags: ["autodocs"],
    args: {
      current: "#overview",
      items: [
        { label: "Home", href: "#overview" },
        { label: "Citation", href: "#citation" },
      ],
    },
  });
</script>

<!-- Navbar with links. -->
<Story
  name="Default"
  play={async ({ canvas, step }) => {
    const nav = canvas.getByRole("navigation");
    await step("Navbar renders", async () => {
      await expect(nav).toBeVisible();
    });
    const items = within(nav).getAllByRole("link");
    await step("Navbar has correct items", async () => {
      await expect(items).toHaveLength(2);

      await expect(items[0]).toHaveAccessibleName("01 Home");
      await expect(items[0]).toHaveAttribute("href", "/#overview");
      await expect(items[0]).toHaveAttribute("aria-current", "location");

      await expect(items[1]).toHaveAccessibleName("02 Citation");
      await expect(items[1]).toHaveAttribute("href", "/#citation");
      await expect(items[1]).not.toHaveAttribute("aria-current");
    });
  }}
/>
