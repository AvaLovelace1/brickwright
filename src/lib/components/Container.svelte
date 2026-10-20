<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ClassValue } from "svelte/elements";

  interface Props {
    class?: ClassValue;
    children: Snippet;
  }
  let { class: className = "", children }: Props = $props();
</script>

<div class={["w-full max-w-4xl flex-1 px-4 sm:px-8", className]}>
  {@render children()}
</div>
