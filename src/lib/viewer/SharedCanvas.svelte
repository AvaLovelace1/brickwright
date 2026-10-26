<script lang="ts">
  import type { Snippet } from "svelte";
  import { setViewerHost, ViewerHost } from "#lib/viewer/viewers.svelte.js";

  let { children }: { children: Snippet } = $props();
  const host = setViewerHost(new ViewerHost());
  const drawn = $derived([...host.viewers].filter((viewer) => viewer.model.status !== "idle"));
  const expanded = $derived([...host.viewers].find((viewer) => viewer.expandedWindow));
  // Each canvas loads with its first viewer and stays, keeping its WebGL context for the next ones.
  let inlineOpened = $state(false);
  let expandedOpened = $state(false);

  $effect(() => {
    if (drawn.length) inlineOpened = true;
  });

  $effect(() => {
    if (expanded) expandedOpened = true;
  });

  function offerRetry(canvas: keyof ViewerHost["retry"]) {
    return (_: unknown, reset: () => void) => {
      host.retry[canvas] = () => {
        host.retry[canvas] = undefined;
        reset();
      };
    };
  }
</script>

{@render children()}
{#if inlineOpened}
  <svelte:boundary onerror={offerRetry("inline")}>
    {#await import("./ModelCanvas.svelte") then { default: ModelCanvas }}
      <ModelCanvas viewers={drawn} />
    {/await}
  </svelte:boundary>
{/if}
{#if expandedOpened}
  <div hidden>
    <svelte:boundary onerror={offerRetry("expanded")}>
      {#await import("./ExpandedModel.svelte") then { default: ExpandedModel }}
        <ExpandedModel viewer={expanded} />
      {/await}
    </svelte:boundary>
  </div>
{/if}
