<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, waitFor, within } from "storybook/test";
  import { Tooltip } from "bits-ui";
  import AgentComparison from "./AgentComparison.svelte";

  const { Story } = defineMeta({
    title: "Components/AgentComparison",
    component: AgentComparison,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <Tooltip.Provider>
    <div class="mx-auto max-w-7xl p-4 sm:p-8">
      <AgentComparison />
    </div>
  </Tooltip.Provider>
{/snippet}

<Story
  name="Diagnostic Views"
  play={async ({ canvas, userEvent, step }) => {
    const intersections = canvas.getByRole("checkbox", { name: "Show intersections" });
    const highlight = canvas.getByRole("checkbox", { name: "Highlight colliding/floating bricks" });
    const viewer = canvas.getByRole("figure", { name: "GPT-6 Astra build without BrickWright" });
    const model = within(viewer);

    await step("Intersections start enabled and highlighting starts disabled", async () => {
      await expect(intersections).toBeChecked();
      await expect(highlight).not.toBeChecked();
      viewer.scrollIntoView({ block: "center" });
      await waitFor(() => expect(model.getByText("Intersections", { exact: true })).toBeVisible(), {
        timeout: 45_000,
      });
    });

    await step("The diagnostic checkboxes work independently", async () => {
      await userEvent.click(intersections);
      await expect(model.queryByText("Intersections", { exact: true })).toBeNull();
      await userEvent.click(highlight);
      await expect(highlight).toBeChecked();
      await expect(intersections).not.toBeChecked();
      await userEvent.click(intersections);
      await expect(model.getByText("Intersections", { exact: true })).toBeVisible();
      await expect(highlight).toBeChecked();
    });

    await step("Models without intersections do not show the legend", async () => {
      const validViewer = within(
        canvas.getByRole("figure", { name: "GPT-6 Astra build with BrickWright" }),
      );
      await waitFor(
        () => expect(validViewer.getByRole("button", { name: "Rewind" })).toBeVisible(),
        { timeout: 45_000 },
      );
      await expect(validViewer.queryByText("Intersections", { exact: true })).toBeNull();
    });
  }}
/>
