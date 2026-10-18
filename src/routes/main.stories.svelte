<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Page from "./+page.svelte";
  import { expect, within } from "storybook/test";
  import { Tooltip as BitsTooltip } from "bits-ui";

  const { Story } = defineMeta({
    title: "Pages/Main Page",
    component: Page,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <BitsTooltip.Provider><Page /></BitsTooltip.Provider>
{/snippet}

<Story
  name="Default"
  play={async ({ canvas, step, userEvent }) => {
    await step("Page has a styled heading", async () => {
      const heading = canvas.getByRole("heading", { level: 1 });
      await expect(heading).toBeVisible();
      const headingStyle = window.getComputedStyle(heading);
      await expect(headingStyle.fontFamily).toContain("Rokkitt");
    });
    await step("Page has a styled paragraph", async () => {
      const paragraph = canvas.queryAllByRole("paragraph")[0];
      await expect(paragraph).toBeVisible();
      const paragraphStyle = window.getComputedStyle(paragraph);
      await expect(paragraphStyle.fontFamily).toContain("Source Sans");
    });
    await step("The comparison figures have independent diagnostic controls", async () => {
      const overview = within(canvas.getByRole("region", { name: "Overview" }));
      const motivation = within(canvas.getByRole("region", { name: "Motivation" }));
      await userEvent.click(
        motivation.getByRole("checkbox", { name: "Highlight colliding bricks" }),
      );
      await expect(
        overview.getByRole("checkbox", { name: "Highlight colliding bricks" }),
      ).not.toBeChecked();
      await userEvent.click(overview.getByRole("checkbox", { name: "Show intersections" }));
      await expect(motivation.getByRole("checkbox", { name: "Show intersections" })).toBeChecked();
      await expect(
        motivation.getByRole("checkbox", { name: "Highlight colliding bricks" }),
      ).toBeChecked();
    });
  }}
/>
