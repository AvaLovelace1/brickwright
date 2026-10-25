<script lang="ts">
  import { onDestroy, type Snippet } from "svelte";
  import { expandedView, inlineCanvas, viewers, type CanvasState } from "#lib/viewers.svelte.js";

  let { children }: { children?: Snippet } = $props();
  const drawn = $derived([...viewers].filter((viewer) => viewer.model.status !== "idle"));
  // Each canvas loads with its first viewer and stays, keeping its WebGL context for the next ones.
  let inlineOpened = $state(false);
  let expandedOpened = $state(false);

  $effect(() => {
    if (drawn.length) inlineOpened = true;
  });

  $effect(() => {
    if (expandedView.window) expandedOpened = true;
  });

  // The canvases leave with this host, so a later host starts without their failures.
  onDestroy(() => {
    inlineCanvas.retry = undefined;
    expandedView.retry = undefined;
  });

  function offerRetry(canvas: CanvasState) {
    return (_: unknown, reset: () => void) => {
      canvas.retry = () => {
        canvas.retry = undefined;
        reset();
      };
    };
  }
</script>

{@render children?.()}
{#if inlineOpened}
  <svelte:boundary onerror={offerRetry(inlineCanvas)}>
    {#await import("./ModelCanvas.svelte") then { default: ModelCanvas }}
      <ModelCanvas viewers={drawn} />
    {/await}
  </svelte:boundary>
{/if}
{#if expandedOpened}
  <div hidden>
    <svelte:boundary onerror={offerRetry(expandedView)}>
      {#await import("./ExpandedModel.svelte") then { default: ExpandedModel }}
        <ExpandedModel />
      {/await}
    </svelte:boundary>
  </div>
{/if}
