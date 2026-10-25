<script lang="ts">
  import type { Snippet } from "svelte";

  let { children }: { children: Snippet } = $props();
</script>

<div
  class={[
    "prose max-w-none prose-bb prose-headings:font-extrabold prose-h2:text-3xl prose-a:hover:text-link-hover",
    "prose-a:active:bg-primary prose-a:active:text-ink",
    "prose-a:focus-visible:outline-2 prose-a:focus-visible:outline-offset-2 prose-a:focus-visible:outline-line",
    "prose-code:before:content-none prose-code:after:content-none prose-ul:list-[square]",
  ]}
>
  {@render children()}
</div>
