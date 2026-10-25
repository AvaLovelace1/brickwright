<script lang="ts">
  import { createModel } from "#lib/models.js";
  import ModelViewer from "#lib/components/ModelViewer.svelte";
  import { resultModelName, type Agent, type ResultPrompt } from "#lib/experiment-results.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  interface Props extends DiagnosticDisplay {
    agent: Agent;
    prompt: ResultPrompt;
    showModels: boolean;
  }

  let { agent, prompt, showModels, ...display }: Props = $props();
  const uid = $props.id();
  const methodLabel = (side: number) => (side === 0 ? agent.baseline : "BrickWright");

  let models = $state(
    (["baseline", "brickwright"] as const).map((method, side) =>
      createModel(
        `results/${resultModelName(prompt, agent, method)}`,
        `${prompt.title} — ${agent.label} — ${methodLabel(side)}`,
      ),
    ),
  );
</script>

<div class="swiper-no-swiping grid grid-cols-2 grid-rows-[auto_1fr] gap-x-3 gap-y-2 sm:gap-x-6">
  {#each models as model, side (model.ldr)}
    <div
      role="group"
      aria-labelledby="{uid}-title-{side}"
      class="row-span-2 grid min-w-0 grid-rows-subgrid"
    >
      <h4
        id="{uid}-title-{side}"
        class="self-end text-center font-body leading-snug font-semibold text-pretty"
      >
        {methodLabel(side)} ({agent.label})
      </h4>
      {#if showModels}
        <ModelViewer bind:model={models[side]} class="aspect-square min-w-0" {...display} />
      {:else}
        <div class="aspect-square bg-surface" aria-hidden="true"></div>
      {/if}
    </div>
  {/each}
</div>
