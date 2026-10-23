<script lang="ts">
  import { Canvas } from "@threlte/core";
  import LegoModel from "#lib/components/LegoModel.svelte";
  import { View } from "@threlte/extras";
  import RenderOnScroll from "./RenderOnScroll.svelte";
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

<div class="pointer-events-none absolute inset-0">
  <Canvas renderMode="manual" dpr={Math.min(window.devicePixelRatio, 2)}>
    <RenderOnScroll />
    {#each models as model, index (model.caption)}
      {#if model.loadRequested}
        <View dom={model.window}>
          <LegoModel bind:model={models[index]} {highlightCollisions} {showIntersections} />
        </View>
      {/if}
    {/each}
  </Canvas>
</div>
