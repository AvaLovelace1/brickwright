<script lang="ts">
  import { asset } from "$app/paths";
  import ModelViewer, { type LegoModelView } from "#lib/components/ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";
  import { resultModelName, type Agent, type ResultPrompt } from "#lib/experiment-results.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  interface Props extends DiagnosticDisplay {
    agent: Agent;
    prompt: ResultPrompt;
    showModels: boolean;
  }

  let { agent, prompt, showModels, showIntersections, highlightCollisions }: Props = $props();
  const uid = $props.id();

  function createModels(): LegoModelView[] {
    return (["baseline", "brickwright"] as const).map((method) => {
      const path = `models/results/${resultModelName(prompt, agent, method)}` as const;
      return {
        ldr: asset(`${path}.ldr`),
        ldrPacked: asset(`${path}.packed.mpd`),
        diagnosticsUrl: asset(`${path}.diagnostics.json`),
        caption: `${prompt.title} — ${agent.label} — ${method === "baseline" ? agent.baseline : "BrickWright"}`,
        stepsShown: 1,
        maxSteps: 1,
      };
    });
  }
  // The parent remounts when the agent or showModels changes, resetting the viewer state.
  let models = $state(createModels());
</script>

<div
  class="swiper-no-swiping relative grid grid-cols-2 grid-rows-[auto_1fr] gap-x-3 gap-y-2 sm:gap-x-6"
>
  {#each models as model, side (model.ldr)}
    <!-- Share the heading row so wrapped titles keep both viewers aligned. -->
    <div
      role="group"
      aria-labelledby="{uid}-title-{side}"
      class="row-span-2 grid min-w-0 grid-rows-subgrid"
    >
      <h4
        id="{uid}-title-{side}"
        class="self-end text-center font-body leading-snug font-semibold text-pretty"
      >
        {side === 0 ? agent.baseline : "BrickWright"} ({agent.label})
      </h4>
      {#if showModels}
        <ModelViewer
          bind:model={models[side]}
          class="aspect-square min-w-0"
          showCaption={false}
          {showIntersections}
          {highlightCollisions}
        />
      {:else}
        <div class="aspect-square bg-surface" aria-hidden="true"></div>
      {/if}
    </div>
  {/each}
  {#if showModels}
    <SharedCanvas {models} {showIntersections} {highlightCollisions} />
  {/if}
</div>
