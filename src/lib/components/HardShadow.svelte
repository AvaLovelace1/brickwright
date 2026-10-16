<script lang="ts">
  import type { Snippet } from "svelte";
  import type { ClassValue } from "svelte/elements";

  interface Props {
    class?: ClassValue;
    bgClass?: ClassValue;
    children: Snippet;
  }
  let { class: className = "", bgClass = "bg-line", children }: Props = $props();
</script>

<div class={["relative isolate", className]}>
  <div
    aria-hidden="true"
    class={[
      "absolute top-[calc(100%-2px)] left-0 -z-1 h-1 w-[calc(100%-2px)] origin-top-left skew-x-45",
      bgClass,
    ]}
  ></div>
  <div
    aria-hidden="true"
    class={[
      "absolute top-0 left-[calc(100%-2px)] -z-1 h-[calc(100%-2px)] w-1 origin-top-left skew-y-45",
      bgClass,
    ]}
  ></div>
  {@render children()}
</div>
