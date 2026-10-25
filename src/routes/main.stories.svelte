<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Page from "./+page.svelte";
  import { expect, within } from "storybook/test";
  import { expectControlsAboveCanvas, waitForView } from "#lib/story-helpers.js";

  const { Story } = defineMeta({
    title: "Pages/Main Page",
    component: Page,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

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

<Story
  name="Viewer Controls"
  play={async ({ canvasElement }) => {
    for (const figure of canvasElement.querySelectorAll<HTMLElement>("figure[aria-busy]")) {
      await waitForView(figure);
      expectControlsAboveCanvas(figure);
    }
  }}
/>
