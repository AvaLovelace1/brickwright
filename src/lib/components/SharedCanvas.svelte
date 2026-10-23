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

{#if models.some((model) => model.status !== "idle")}
  <!-- Rebuilding the canvas when models enter or leave the error state lets Retry recover from a canvas that failed to start. -->
  {#key models.some((model) => model.status === "error")}
    <svelte:boundary
      onerror={() => {
        for (const model of models) {
          if (model.status !== "idle") model.status = "error";
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
