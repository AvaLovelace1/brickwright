<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ClassValue } from "svelte/elements";

  interface Props {
    class?: ClassValue;
    children: Snippet;
  }
  let { class: className = "", children }: Props = $props();
</script>

<div
  class={[
    "mx-auto prose max-w-none prose-bb prose-headings:font-extrabold prose-h2:text-3xl prose-a:hover:text-link-hover",
    "prose-code:before:content-none prose-code:after:content-none prose-ul:list-[square]",
    className,
  ]}
>
  {@render children()}
</div>
