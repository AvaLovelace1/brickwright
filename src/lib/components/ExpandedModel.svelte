<script lang="ts">
  import { Canvas } from "@threlte/core";
  import ViewerModel from "./ViewerModel.svelte";
  import { expandedView } from "#lib/viewers.svelte.js";

  // Every expanded dialog borrows this canvas while open, so they share one WebGL context.
  function moveIntoDialog(element: HTMLElement) {
    const target = expandedView.window;
    if (!target) return;
    target.append(element);
    return () => element.remove();
  }
</script>

<div class="size-full" {@attach moveIntoDialog}>
  <Canvas dpr={Math.min(window.devicePixelRatio, 2)}>
    {#key expandedView.viewer}
      {#if expandedView.viewer}
        <ViewerModel viewer={expandedView.viewer} view="expanded" />
      {/if}
    {/key}
  </Canvas>
</div>
