<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ClassValue } from "svelte/elements";

  const {
    href,
    class: className,
    children,
  }: { href: string; class?: ClassValue; children: Snippet } = $props();
</script>

<a {href} class={className} target="_blank" rel="external noopener">{@render children()}</a>
