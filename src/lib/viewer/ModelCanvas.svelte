<script lang="ts">
  import { Canvas } from "@threlte/core";
  import ElementView from "./ElementView.svelte";
  import FollowViewport from "./FollowViewport.svelte";
  import ViewerModel from "./ViewerModel.svelte";
  import type { Viewer } from "#lib/viewer/viewers.svelte.js";

  let { viewers }: { viewers: Viewer[] } = $props();
</script>

<!-- The canvas lies beneath viewer controls, the header, and dialogs. -->
<div class="pointer-events-none absolute inset-x-0 top-0 z-1 h-[200lvh]">
  <Canvas renderMode="manual" dpr={Math.min(window.devicePixelRatio, 2)}>
    <FollowViewport />
    {#each viewers as viewer (viewer)}
      {#if viewer.window}
        <ElementView dom={viewer.window}>
          <ViewerModel {viewer} />
        </ElementView>
      {/if}
    {/each}
  </Canvas>
</div>
