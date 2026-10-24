<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<div
  class={[
    "prose max-w-none prose-bb prose-headings:font-extrabold prose-h2:text-3xl prose-a:hover:text-link-hover",
    "prose-code:before:content-none prose-code:after:content-none prose-ul:list-[square]",
  ]}
>
  {@render children()}
</div>
