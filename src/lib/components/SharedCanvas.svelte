<script lang="ts">
  import { Canvas } from "@threlte/core";
  import LegoModel from "#lib/components/LegoModel.svelte";
  import { View } from "@threlte/extras";
  import type { LegoModelView } from "#lib/components/ModelViewer.svelte";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  interface Props extends Partial<DiagnosticDisplay> {
    models: LegoModelView[];
  }
  let { models, highlightCollisions = false, showIntersections = false }: Props = $props();
</script>

<!-- Set pointer-events-none so the overlay doesn't capture camera drag controls -->
<div class="pointer-events-none absolute inset-0">
  <Canvas>
    {#each models as model (model.caption)}
      {#if model.loadRequested}
        <View dom={model.window}>
          <LegoModel
            {model}
            {highlightCollisions}
            {showIntersections}
            onload={(maxSteps) => {
              model.maxSteps = maxSteps;
              model.loaded = true;
            }}
            ondiagnosticerror={() => (model.diagnosticsError = true)}
          />
        </View>
      {/if}
    {/each}
  </Canvas>
</div>
