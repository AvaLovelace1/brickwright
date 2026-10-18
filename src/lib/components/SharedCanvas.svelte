<script lang="ts">
  import { Canvas } from "@threlte/core";
  import LegoModel from "#lib/components/LegoModel.svelte";
  import { View } from "@threlte/extras";
  import type { LegoModelView } from "#lib/components/ModelViewer.svelte";

  interface Props {
    models: LegoModelView[];
  }
  let { models = $bindable() }: Props = $props();
</script>

<!-- Set pointer-events-none so the overlay doesn't capture camera drag controls -->
<div class="pointer-events-none absolute inset-0">
  <Canvas>
    {#each models as model (model.caption)}
      {#if model.loadRequested}
        <View dom={model.window}>
          <LegoModel
            ldrPacked={model.ldrPacked}
            bricksShown={model.bricksShown}
            onload={(maxBricks) => {
              model.maxBricks = maxBricks;
              model.loaded = true;
            }}
          />
        </View>
      {/if}
    {/each}
  </Canvas>
</div>
