<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, waitFor, within } from "storybook/test";
  import { isPhysicallyValid, loadDiagnostics } from "#lib/viewer/model-diagnostics.js";
  import { modelFiles } from "#lib/viewer/models.js";
  import { waitForModel } from "#lib/story-helpers.js";
  import ExistingMethods from "./ExistingMethods.svelte";

  const { Story } = defineMeta({
    title: "Content/ExistingMethods",
    component: ExistingMethods,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <div class="mx-auto max-w-7xl p-4 sm:p-8"><ExistingMethods /></div>
{/snippet}

<Story
  name="Diagnostic Views"
  play={async ({ canvas, userEvent, step }) => {
    const figure = within(canvas.getByRole("figure", { name: "Existing methods" }));
    const intersections = figure.getByRole("checkbox", { name: "Show intersections" });

    await step("Each method loads its build and matching diagnostics", async () => {
      for (const [name, run] of [
        ["BrickGPT", "brickgpt"],
        ["BrickNet", "bricknet"],
        ["Codex (GPT-6 Astra)", "codex-astra-docs"],
        ["Codex (GPT-6.1 Sol)", "codex-sol-docs"],
      ]) {
        const viewer = figure.getByRole("figure", { name: `${name} build` });
        const model = within(viewer);
        await waitForModel(viewer);
        await expect(model.getByRole("button", { name: "Rewind" })).toBeVisible();
        await expect(model.getByRole("link", { name: "Download LDraw" })).toBeVisible();
        const diagnostics = await loadDiagnostics(
          modelFiles(`existing-methods/truck-${run}`).diagnosticsUrl!,
        );
        await waitFor(() =>
          expect(model.getByRole("status")).toHaveTextContent(
            isPhysicallyValid(diagnostics) ? /^Valid$/ : /^Invalid$/,
          ),
        );
        const hasIntersections = diagnostics.intersectionPositions.length > 0;
        await waitFor(() =>
          expect(model.queryAllByText("Intersections", { exact: true })).toHaveLength(
            Number(hasIntersections),
          ),
        );
        await expect(model.queryByText("Diagnostics unavailable", { exact: true })).toBeNull();
      }
    });

    await step("The figure control hides intersections across all four models", async () => {
      await userEvent.click(intersections);
      await expect(figure.queryAllByText("Intersections", { exact: true })).toHaveLength(0);
    });
  }}
/>
