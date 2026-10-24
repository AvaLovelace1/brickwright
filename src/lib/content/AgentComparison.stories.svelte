<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, waitFor, within } from "storybook/test";
  import { waitForModel } from "#lib/story-helpers.js";
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
