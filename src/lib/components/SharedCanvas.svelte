<script lang="ts">
  import type { ModelView } from "#lib/models.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  let { models, ...display }: { models: ModelView[] } & Partial<DiagnosticDisplay> = $props();
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
        <ModelCanvas {models} {...display} />
      {/await}
      {#snippet failed()}<span class="sr-only">3D viewer unavailable</span>{/snippet}
    </svelte:boundary>
  {/key}
{/if}
