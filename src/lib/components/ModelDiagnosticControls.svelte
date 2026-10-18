<script lang="ts">
  import type { DiagnosticDisplay } from "#lib/model-diagnostics.js";
  import Checkbox from "./Checkbox.svelte";

  let { showIntersections = $bindable(), highlightCollisions = $bindable() }: DiagnosticDisplay =
    $props();
</script>

<div class="flex flex-wrap gap-x-4 gap-y-2">
  <Checkbox label="Show intersections" bind:checked={showIntersections} />
  <Checkbox label="Highlight colliding bricks" bind:checked={highlightCollisions} />
</div>
