<script lang="ts">
  import ExternalLink from "#lib/components/ExternalLink.svelte";
  import {
    results,
    metricColumns,
    changeOutcome,
    fullAgentName,
    type ResultMetric,
    type MetricDirection,
    type MetricKey,
  } from "#lib/experiment-results.js";

  const methodLinks: Record<string, string> = {
    BrickGPT: "https://avalovelace1.github.io/BrickGPT/",
    BrickNet: "https://kulits.github.io/BrickNet/",
    Articraft: "https://articraft3d.github.io/",
  };
  const metricLinks: Partial<Record<MetricKey, string>> = {
    vqa: "https://linzhiqiu.github.io/papers/vqascore/",
    perceptionEncoder:
      "https://proceedings.neurips.cc/paper_files/paper/2025/hash/57bc0a850255e2041341bf74c7e2b9fa-Abstract-Conference.html",
    siglip2: "https://arxiv.org/abs/2502.14786",
  };
  const uid = $props.id();
  const directionArrows = { higher: "↑", lower: "↓" };
  const deltaClasses = {
    improvement: "text-success-deep dark:text-success-bright",
    regression: "text-danger dark:text-danger-brighter",
  };
</script>

{#snippet metric(cell: ResultMetric, metricDirection: MetricDirection | null)}
  <span
    class={[cell.emphasis === "bold" && "font-bold", cell.emphasis === "underline" && "underline"]}
    >{cell.value}</span
  >
  {#if cell.change}
    {@const outcome = changeOutcome(cell.change, metricDirection)}
    <span class={["block text-xs", outcome && deltaClasses[outcome]]}>({cell.change})</span>
  {/if}
{/snippet}

<h3 id="{uid}-heading" class="text-2xl">Quantitative results</h3>
<!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard access to the horizontally scrolling table.) -->
<div
  role="region"
  aria-labelledby="{uid}-heading"
  tabindex="0"
  class="mt-4 overflow-x-auto bb-border focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line"
>
  <table
    aria-labelledby="{uid}-heading"
    aria-describedby="{uid}-notes"
    class="w-full border-collapse bg-surface text-sm tabular-nums [&_a]:text-link [&_a]:underline [&_a:hover]:text-link-hover"
  >
    <thead class="border-b-2 border-line bg-bg whitespace-nowrap">
      <tr>
        <th scope="col" class="p-3 text-left font-semibold">Agent</th>
        <th scope="col" class="p-3 text-left font-semibold">Method</th>
        {#each metricColumns as column (column.key)}
          {@const href = metricLinks[column.key]}
          <th scope="col" class="p-3 text-right font-semibold">
            {#if href}
              <ExternalLink {href}>{column.label}</ExternalLink>
            {:else}
              {column.label}
            {/if}{column.direction ? ` ${directionArrows[column.direction]}` : ""}
          </th>
        {/each}
      </tr>
    </thead>
    <tbody>
      {#each results as row, index (`${row.agent}-${row.method}`)}
        {@const isBrickWright = row.method === "BrickWright"}
        {@const startsAgentGroup = index > 0 && row.agent !== results[index - 1].agent}
        {@const href = methodLinks[row.method]}
        <tr class={[startsAgentGroup && "border-t-2 border-line", isBrickWright && "bg-bg"]}>
          <td class="p-3 align-top whitespace-nowrap">{fullAgentName(row.agent)}</td>
          <th
            scope="row"
            class={[
              "p-3 text-left align-top whitespace-nowrap",
              isBrickWright ? "font-bold" : "font-normal",
            ]}
          >
            {#if href}
              <ExternalLink class="font-medium" {href}>{row.method}</ExternalLink>
            {:else}
              <span class={[isBrickWright && "border-l-4 border-primary pl-2"]}>{row.method}</span>
            {/if}
          </th>
          {#each metricColumns as column (column.key)}
            <td class="p-3 text-right align-top whitespace-nowrap">
              {@render metric(row.metrics[column.key], column.direction)}
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<div id="{uid}-notes" class="mt-4 text-sm text-pretty">
  <p>
    We report the proportion of prompts yielding valid builds (no collisions or floaters),
    collision-free builds, and floater-free builds. Components and Bricks are the mean
    connected-component and part count, respectively. ↑ means higher is better; ↓ means lower is
    better. Parentheses show absolute changes from the matching Claude Code or Codex baseline. Time
    and cost are averages per prompt; costs use October 2026 token pricing, including cache savings.
  </p>
</div>
