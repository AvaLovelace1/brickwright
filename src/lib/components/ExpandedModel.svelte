<script lang="ts">
  import { Canvas } from "@threlte/core";
  import LegoModel from "./LegoModel.svelte";
  import type { ModelView } from "#lib/models.js";
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";

  let {
    model,
    highlightCollisions,
    showIntersections,
  }: {
    model: ModelView;
  } & DiagnosticDisplay = $props();
</script>

<Canvas dpr={Math.min(window.devicePixelRatio, 2)}>
  <LegoModel {model} {highlightCollisions} {showIntersections} expanded />
</Canvas>
