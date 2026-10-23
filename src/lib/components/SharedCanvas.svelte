<script lang="ts">
  import type { ModelView } from "#lib/models.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  interface Props extends Partial<DiagnosticDisplay> {
    models: ModelView[];
  }
  let {
    models = $bindable(),
    highlightCollisions = false,
    showIntersections = false,
  }: Props = $props();
</script>

{#if models.some((model) => model.loadRequested)}
  {#key models.map((model) => model.loadAttempt ?? 0).join(",")}
    <svelte:boundary
      onerror={() => {
        for (const model of models) {
          if (model.loadRequested) model.loadError = true;
        }
      }}
    >
      {#await import("./ModelCanvas.svelte") then { default: ModelCanvas }}
        <ModelCanvas {models} {highlightCollisions} {showIntersections} />
      {/await}
      {#snippet failed()}<span class="sr-only">3D viewer unavailable</span>{/snippet}
    </svelte:boundary>
  {/key}
{/if}
