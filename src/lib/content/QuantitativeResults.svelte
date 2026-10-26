<script lang="ts">
  import ExternalLink from "#lib/components/ExternalLink.svelte";
  import {
    results,
    metricColumns,
    fullAgentName,
    metricEmphasis,
  } from "#lib/content/experiment-results.js";

  const uid = $props.id();
  const directionArrows = { higher: "↑", lower: "↓" };
</script>

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
    class="w-full border-collapse bg-surface text-sm tabular-nums [&_a]:text-link [&_a]:underline [&_a]:hover:text-link-hover [&_a]:focus-visible:outline-2 [&_a]:focus-visible:outline-offset-2 [&_a]:focus-visible:outline-line [&_a]:active:bg-primary [&_a]:active:text-ink"
  >
    <thead class="border-b-2 border-line bg-bg whitespace-nowrap">
      <tr>
        <th scope="col" class="p-3 text-left font-semibold">Agent</th>
        <th scope="col" class="p-3 text-left font-semibold">Method</th>
        {#each metricColumns as column (column.key)}
          <th scope="col" class="p-3 text-right font-semibold">
            {#if "href" in column}
              <ExternalLink href={column.href}>{column.label}</ExternalLink>
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
        <tr class={[startsAgentGroup && "border-t-2 border-line", isBrickWright && "bg-bg"]}>
          <td class="p-3 align-top whitespace-nowrap">{fullAgentName(row.agent)}</td>
          <th
            scope="row"
            class={[
              "p-3 text-left align-top whitespace-nowrap",
              isBrickWright ? "font-bold" : "font-normal",
            ]}
          >
            {#if row.href}
              <ExternalLink class="font-medium" href={row.href}>{row.method}</ExternalLink>
            {:else}
              <span class={[isBrickWright && "border-l-4 border-primary pl-2"]}>{row.method}</span>
            {/if}
          </th>
          {#each metricColumns as column (column.key)}
            {@const emphasis = metricEmphasis(row, column)}
            <td class="p-3 text-right align-top whitespace-nowrap">
              <span
                class={[
                  emphasis === "bold" && "font-bold",
                  emphasis === "underline" && "underline",
                ]}>{row.metrics[column.key]}</span
              >
            </td>
          {/each}
        </tr>
      {/each}
    </tbody>
  </table>
</div>
<p id="{uid}-notes" class="mt-4 text-sm text-pretty">
  We report the proportion of prompts yielding valid builds (no collisions or floaters),
  collision-free builds, and floater-free builds. Components, Parts, and Unique parts are the mean
  connected-component, part, and distinct part-ID counts. Checks is the mean number of
  <code>validate</code> calls. ↑ means higher is better; ↓ means lower is better. Bold and underline mark
  the best and second-best results within each agent. Time and cost are averages per prompt; costs use
  October 2026 token pricing, including cache savings.
</p>
