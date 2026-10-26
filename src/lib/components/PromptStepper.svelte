<script lang="ts">
  import type { ClassValue } from "svelte/elements";
  import Button from "./Button.svelte";

  interface Props {
    /** The shown prompt's zero-based index. */
    index: number;
    count: number;
    onprevious: () => void;
    onnext: () => void;
    class?: ClassValue;
  }
  let { index, count, onprevious, onnext, class: className = "" }: Props = $props();
</script>

<div class={["bb-btn-container flex shrink-0 items-center gap-3 pt-1 pl-1", className]}>
  <Button text="Previous prompt" action={onprevious} icon="tdesign--chevron-left" iconOnly />
  <p
    role="status"
    aria-label="Prompt position"
    aria-live="polite"
    aria-atomic="true"
    class="relative -top-1 -left-0.5 min-w-8 text-center tabular-nums"
  >
    {index + 1} / {count}
  </p>
  <Button text="Next prompt" action={onnext} icon="tdesign--chevron-right" iconOnly />
</div>
