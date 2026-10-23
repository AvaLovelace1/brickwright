<script lang="ts">
  import type { ClassValue } from "svelte/elements";

  let { class: className = "" }: { class?: ClassValue } = $props();
</script>

<span class={["inline-block size-[0.25em] bg-current align-middle", className]} aria-hidden="true"
></span>
