<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, within } from "storybook/test";
  import QuantitativeResults from "./QuantitativeResults.svelte";
  import { fullAgentName, results, metricColumns } from "#lib/experiment-results.js";

  const { Story } = defineMeta({
    title: "Content/QuantitativeResults",
    component: QuantitativeResults,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
    play: ({ canvasElement }) => checkTable(canvasElement),
  });

  async function checkTable(element: HTMLElement) {
    const canvas = within(element);
    await expect(canvas.getAllByRole("table")).toHaveLength(1);
    const table = within(canvas.getByRole("table", { name: "Quantitative results" }));
    await expect(table.getAllByRole("columnheader")).toHaveLength(metricColumns.length + 2);
    const rows = table.getAllByRole("row").slice(1);
    await expect(rows).toHaveLength(results.length);
    for (const [index, result] of results.entries()) {
      const row = within(rows[index]);
      const [agentCell, ...metricCells] = row.getAllByRole("cell");
      await expect(agentCell.textContent).toBe(fullAgentName(result.agent));
      await expect(row.getByRole("rowheader").textContent).toBe(result.method);
      await expect(metricCells).toHaveLength(metricColumns.length);
      for (const [columnIndex, column] of metricColumns.entries())
        await expect(metricCells[columnIndex].textContent?.trim()).toBe(result.metrics[column.key]);
    }
  }
</script>

{#snippet template()}
  <div class="mx-auto max-w-7xl p-4 sm:p-8"><QuantitativeResults /></div>
{/snippet}

<Story name="Results" />

<Story name="Dark" globals={{ theme: "dark" }} />

<Story
  name="Narrow Container"
  play={async ({ canvas, canvasElement }) => {
    await checkTable(canvasElement);
    const scroller = canvas.getByRole("region", { name: "Quantitative results" });
    scroller.focus();
    await expect(scroller).toHaveFocus();
    await expect(scroller.getBoundingClientRect().width).toBeLessThanOrEqual(390);
    await expect(scroller.scrollWidth).toBeGreaterThan(scroller.clientWidth);
  }}
>
  {#snippet template()}
    <div class="w-97.5 max-w-full p-4"><QuantitativeResults /></div>
  {/snippet}
</Story>
