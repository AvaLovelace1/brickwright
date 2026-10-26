<script lang="ts">
  import LegoModel from "./LegoModel.svelte";
  import type { Viewer } from "#lib/viewer/viewers.svelte.js";

  let { viewer, view }: { viewer: Viewer; view?: "inline" | "expanded" } = $props();
</script>

<!-- A model that fails to draw is marked as errored, and Retry model mounts it afresh. -->
{#if viewer.model.status !== "error"}
  <svelte:boundary onerror={() => viewer.failed()}>
    <LegoModel {viewer} {view} />
  </svelte:boundary>
{/if}
