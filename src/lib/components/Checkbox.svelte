<script lang="ts">
  import { Checkbox as BitsCheckbox } from "bits-ui";

  let { label, checked = $bindable(false) }: { label: string; checked?: boolean } = $props();
  const uid = $props.id();
</script>

<div class="inline-flex items-center gap-2">
  <BitsCheckbox.Root
    id={uid}
    bind:checked
    class={[
      "inline-flex size-4 shrink-0 items-center justify-center",
      "cursor-pointer bb-border bg-surface text-ink",
      "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line",
      "data-[state=checked]:bg-primary",
    ]}
  >
    {#snippet children({ checked })}
      {#if checked}<span class="iconify tdesign--check" aria-hidden="true"></span>{/if}
    {/snippet}
  </BitsCheckbox.Root>
  <label for={uid} class="cursor-pointer text-sm font-semibold">{label}</label>
</div>
