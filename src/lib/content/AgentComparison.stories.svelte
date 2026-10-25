<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor, within } from "storybook/test";
  import { waitForModel, waitForView } from "#lib/story-helpers.js";
  import AgentComparison from "./AgentComparison.svelte";

  const { Story } = defineMeta({
    title: "Content/AgentComparison",
    component: AgentComparison,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <div class="mx-auto max-w-7xl p-4 sm:p-8"><AgentComparison /></div>
{/snippet}

<Story
  name="Diagnostic Views"
  play={async ({ canvas, userEvent, step }) => {
    const intersections = canvas.getByRole("checkbox", { name: "Show intersections" });
    const viewer = canvas.getByRole("figure", { name: "GPT-6 Astra build without BrickWright" });
    const model = within(viewer);

    await step("The baseline model shows its intersections", async () => {
      await waitForModel(viewer);
      await waitFor(() => expect(model.getByText("Intersections", { exact: true })).toBeVisible());
    });
    await step("Models without intersections do not show the legend", async () => {
      const validViewer = canvas.getByRole("figure", {
        name: "GPT-6 Astra build with BrickWright",
      });
      await waitForModel(validViewer);
      await expect(within(validViewer).getByRole("button", { name: "Rewind" })).toBeVisible();
      await expect(within(validViewer).queryByText("Intersections", { exact: true })).toBeNull();
    });
    await step("The comparison control hides the baseline's intersections", async () => {
      await userEvent.click(intersections);
      await expect(model.queryByText("Intersections", { exact: true })).toBeNull();
    });
  }}
/>

<Story
  name="Shared Canvases"
  parameters={{ a11y: { context: "body" } }}
  play={async ({ canvasElement, userEvent, step }) => {
    const viewers = [...canvasElement.querySelectorAll<HTMLElement>("figure[aria-busy]")];

    await step("One canvas draws every viewer", async () => {
      for (const viewer of viewers) await waitForView(viewer);
      await expect(document.querySelectorAll("canvas")).toHaveLength(1);
    });
    await step("The canvas scrolls with its viewers between redraws", async () => {
      viewers[0].scrollIntoView({ block: "center" });
      const view = within(viewers[0]).getByRole("group", { name: /interactive 3D view/ });
      const elements = [document.querySelector("canvas")!, view];
      const before = elements.map((element) => element.getBoundingClientRect().top);
      // Scrolling within one task leaves no frame for the canvas to redraw.
      scrollBy(0, 100);
      const shifts = elements.map((element, i) => before[i] - element.getBoundingClientRect().top);
      await expect(shifts).toEqual([100, 100]);
    });
    await step("Expanded views draw on a second canvas", async () => {
      // Leave the dialog open for the accessibility audit.
      await userEvent.click(within(viewers[0]).getByRole("button", { name: "Expand view" }));
      const dialog = await screen.findByRole("dialog", { name: "Expanded model view" });
      await waitFor(() => expect(dialog.querySelector("canvas")).not.toBeNull());
      await expect(document.querySelectorAll("canvas")).toHaveLength(2);
    });
  }}
/>
