<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import ModelDiagnosticControls from "./ModelDiagnosticControls.svelte";

  const { Story } = defineMeta({
    title: "Components/ModelDiagnosticControls",
    component: ModelDiagnosticControls,
    tags: ["autodocs"],
  });
</script>

<script lang="ts">
  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
</script>

<Story
  name="Independent Toggles"
  play={async ({ canvas, userEvent, step }) => {
    const intersections = canvas.getByRole("checkbox", { name: "Show intersections" });
    const highlight = canvas.getByRole("checkbox", { name: "Highlight colliding bricks" });
    const boundValues = canvas.getByRole("status");

    async function expectState(showIntersections: boolean, highlightCollisions: boolean) {
      if (showIntersections) await expect(intersections).toBeChecked();
      else await expect(intersections).not.toBeChecked();
      if (highlightCollisions) await expect(highlight).toBeChecked();
      else await expect(highlight).not.toBeChecked();
      await expect(boundValues).toHaveTextContent(
        `Intersections: ${showIntersections}; Highlighting: ${highlightCollisions}`,
      );
    }

    await step("The controls reflect their parent's initial values", async () => {
      await expectState(true, false);
    });
    await step("Each toggle updates its binding without changing the other", async () => {
      await userEvent.click(intersections);
      await expectState(false, false);
      await userEvent.click(highlight);
      await expectState(false, true);
      await userEvent.click(intersections);
      await expectState(true, true);
      await userEvent.click(highlight);
      await expectState(true, false);
    });
  }}
>
  {#snippet template()}
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
    <p class="mt-2 text-sm" role="status">
      Intersections: {showIntersections}; Highlighting: {highlightCollisions}
    </p>
  {/snippet}
</Story>
