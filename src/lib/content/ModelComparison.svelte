<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ModelView } from "#lib/viewer/models.js";
  import ModelDiagnosticControls from "#lib/viewer/ModelDiagnosticControls.svelte";
  import ModelViewer from "#lib/viewer/ModelViewer.svelte";

  interface Props {
    title: string;
    prompt: string;
    groups: { name: string; models: (ModelView & { label: string })[] }[];
    caption: Snippet;
  }

  let { title, prompt, groups = $bindable(), caption }: Props = $props();
  const uid = $props.id();
  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
</script>

<figure aria-labelledby="{uid}-title" aria-describedby="{uid}-caption">
  <div class="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
    <p id="{uid}-title" class="font-display text-2xl font-extrabold">{title}</p>
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
  </div>
  <p class="mb-6 text-sm text-pretty">
    <span class="font-bold">Prompt:</span>
    <span class="italic">“{prompt}”</span>
  </p>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    {#each groups as group (group.name)}
      <div class="min-w-0">
        <p class="mb-3 border-b border-line pb-1 text-center font-display text-xl font-extrabold">
          {group.name}
        </p>
        <div class="grid grid-cols-2 gap-3">
          {#each group.models as model, i (model.ldr)}
            <div class="min-w-0">
              <p class="mb-1 text-center font-semibold">{model.label}</p>
              <ModelViewer
                bind:model={group.models[i]}
                class="aspect-square"
                {highlightCollisions}
                {showIntersections}
              />
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
  <figcaption id="{uid}-caption" class="mt-6 text-sm text-pretty">
    {@render caption()}
  </figcaption>
</figure>
