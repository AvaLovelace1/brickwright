<script lang="ts">
  import { Canvas } from "@threlte/core";
  import ViewerModel from "./ViewerModel.svelte";
  import type { Viewer } from "#lib/viewer/viewers.svelte.js";

  let { viewer }: { viewer?: Viewer } = $props();

  // Every expanded dialog borrows this canvas while open, so they share one WebGL context.
  function moveIntoDialog(element: HTMLElement) {
    const target = viewer?.expandedWindow;
    if (!target) return;
    target.append(element);
    return () => element.remove();
  }
</script>

<div class="size-full" {@attach moveIntoDialog}>
  <Canvas dpr={Math.min(window.devicePixelRatio, 2)}>
    {#key viewer}
      {#if viewer}
        <ViewerModel {viewer} view="expanded" />
      {/if}
    {/key}
  </Canvas>
</div>
