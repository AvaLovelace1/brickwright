<script lang="ts">
  import { Canvas } from "@threlte/core";
  import LegoModel from "./LegoModel.svelte";
  import { View } from "@threlte/extras";
  import RenderOnScroll from "./RenderOnScroll.svelte";
  import type { ModelView } from "#lib/models.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  let { models = $bindable(), ...display }: { models: ModelView[] } & Partial<DiagnosticDisplay> =
    $props();
</script>

<div class="pointer-events-none absolute inset-0">
  <Canvas renderMode="manual" dpr={Math.min(window.devicePixelRatio, 2)}>
    <RenderOnScroll />
    {#each models as model, index (model.caption)}
      {#if model.status !== "idle"}
        <View dom={model.window}>
          <LegoModel bind:model={models[index]} {...display} />
        </View>
      {/if}
    {/each}
  </Canvas>
</div>
