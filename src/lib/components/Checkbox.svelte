<script lang="ts">
  import { Checkbox as BitsCheckbox } from "bits-ui";
  import type { ClassValue } from "svelte/elements";

  export interface Props {
    label: string;
    checked?: boolean;
    disabled?: boolean;
    class?: ClassValue;
  }

  let {
    label,
    checked = $bindable(false),
    disabled = false,
    class: className = "",
  }: Props = $props();
  const uid = $props.id();
</script>

<div class="inline-flex items-center gap-2">
  <BitsCheckbox.Root
    id={uid}
    bind:checked
    {disabled}
    class={[
      "peer inline-flex size-4 shrink-0 items-center justify-center",
      "cursor-pointer bb-border bg-surface text-ink",
      "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line",
      "disabled:cursor-not-allowed disabled:opacity-50",
      "data-[state=checked]:bg-primary",
      className,
    ]}
  >
    {#snippet children({ checked })}
      {#if checked}<span class="iconify tdesign--check" aria-hidden="true"></span>{/if}
    {/snippet}
  </BitsCheckbox.Root>
  <label
    for={uid}
    class={[
      "cursor-pointer text-sm font-semibold",
      "peer-disabled:cursor-not-allowed peer-disabled:opacity-50",
    ]}
  >
    {label}
  </label>
</div>
