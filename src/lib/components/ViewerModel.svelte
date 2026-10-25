<script lang="ts">
  import LegoModel from "./LegoModel.svelte";
  import type { Viewer } from "#lib/viewers.svelte.js";

  let { viewer, view }: { viewer: Viewer; view?: "inline" | "expanded" } = $props();
</script>

<!-- A model that fails to draw is marked as errored, and Retry model remounts it. -->
{#key viewer.model.status === "error"}
  <svelte:boundary onerror={() => viewer.failed()}>
    <LegoModel
      model={viewer.model}
      highlightCollisions={viewer.highlightCollisions}
      showIntersections={viewer.showIntersections}
      {view}
      onload={(steps) => viewer.loaded(steps)}
      onerror={() => viewer.failed()}
    />
  </svelte:boundary>
{/key}
