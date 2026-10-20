<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { Tooltip } from "bits-ui";
  import { expect, waitFor, within } from "storybook/test";
  import { loadDiagnostics } from "#lib/model-diagnostics.js";
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
  <Tooltip.Provider>
    <div class="mx-auto max-w-7xl p-4 sm:p-8">
      <ExistingMethods />
    </div>
  </Tooltip.Provider>
{/snippet}

<Story
  name="Diagnostic Views"
  play={async ({ canvas, userEvent, step }) => {
    const figure = within(canvas.getByRole("figure", { name: "Existing methods" }));
    const intersections = figure.getByRole("checkbox", { name: "Show intersections" });

    await step("Each method loads its build and matching diagnostics", async () => {
      for (const name of ["BrickGPT", "BrickNet", "Codex (GPT-6 Astra)", "Codex (GPT-6.1 Sol)"]) {
        const viewer = figure.getByRole("figure", { name: `${name} build` });
        const model = within(viewer);
        viewer.scrollIntoView({ block: "center" });
        await waitFor(() => expect(model.getByRole("button", { name: "Rewind" })).toBeVisible(), {
          timeout: 45_000,
        });
        const download = model.getByRole("link", { name: "Download LDraw" });
        await expect(download).toBeVisible();
        const diagnostics = await loadDiagnostics(
          download.getAttribute("href")!.replace(/\.ldr$/, ".diagnostics.json"),
        );
        const valid = diagnostics.collisions.length === 0 && diagnostics.floating.length === 0;
        await waitFor(() =>
          expect(model.getByRole("status")).toHaveTextContent(valid ? /^Valid$/ : /^Invalid$/),
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
