<script lang="ts">
  import { RadioGroup as BitsRadioGroup } from "bits-ui";
  import type { ClassValue } from "svelte/elements";

  export interface RadioOption {
    value: string;
    label: string;
    disabled?: boolean;
  }

  export interface Props {
    label: string;
    options: RadioOption[];
    value?: string;
    hideLabel?: boolean;
    disabled?: boolean;
    class?: ClassValue;
  }

  let {
    label,
    options,
    value = $bindable(""),
    hideLabel = false,
    disabled = false,
    class: className = "",
  }: Props = $props();
  const uid = $props.id();
</script>

<div class="flex flex-wrap items-center gap-x-3 gap-y-2">
  <span id="{uid}-label" class={["text-sm", hideLabel && "sr-only"]}>{label}</span>
  <BitsRadioGroup.Root
    bind:value
    {disabled}
    orientation="horizontal"
    aria-labelledby="{uid}-label"
    class={["bb-btn-group", className]}
  >
    {#each options as option (option.value)}
      <BitsRadioGroup.Item
        value={option.value}
        disabled={option.disabled}
        class={[
          "bb-btn px-3 text-sm focus-visible:z-10",
          value === option.value && "bb-btn-primary",
        ]}
      >
        {option.label}
      </BitsRadioGroup.Item>
    {/each}
  </BitsRadioGroup.Root>
</div>
