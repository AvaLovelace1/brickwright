<script lang="ts">
  import { Select as BitsSelect } from "bits-ui";
  import HardShadow from "./HardShadow.svelte";
  import { fly } from "#lib/motion.svelte.js";
  import type { ClassValue } from "svelte/elements";

  export interface SelectOption {
    value: string;
    label: string;
    disabled?: boolean;
    icon?: string;
  }

  export interface Props {
    label: string;
    options: SelectOption[];
    value?: string;
    hideLabel?: boolean;
    /** Hide the selected label in the trigger; menu options still show their labels. */
    iconOnly?: boolean;
    labelClass?: ClassValue;
    placeholder?: string;
    disabled?: boolean;
    class?: ClassValue;
  }

  let {
    label,
    options,
    value = $bindable(""),
    hideLabel = false,
    iconOnly = false,
    labelClass = "mb-1 text-sm",
    placeholder = "Select an option",
    disabled = false,
    class: className = "",
  }: Props = $props();

  let open = $state(false);
  const uid = $props.id();
  const selectedOption = $derived(options.find((option) => option.value === value));
  const selectedLabel = $derived(selectedOption?.label ?? placeholder);
</script>

<div id="{uid}-label" class={[labelClass, hideLabel && "sr-only"]}>{label}</div>
<BitsSelect.Root type="single" bind:value bind:open allowDeselect={false} {disabled}>
  <BitsSelect.Trigger
    title={iconOnly ? `${label}: ${selectedLabel}` : undefined}
    aria-labelledby="{uid}-label {uid}-value"
    class={[
      "flex cursor-pointer items-center justify-between gap-2 px-3 py-2",
      iconOnly ? "w-auto shrink-0" : "w-full",
      "bb-border bg-surface",
      "text-left text-text",
      "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line",
      "disabled:cursor-not-allowed disabled:opacity-50",
      className,
    ]}
  >
    {#if selectedOption?.icon}
      <span class="iconify {selectedOption.icon} shrink-0" aria-hidden="true"></span>
    {/if}
    <span id="{uid}-value" class:sr-only={iconOnly}>{selectedLabel}</span>
    <span
      class={["iconify shrink-0", open ? "tdesign--chevron-up" : "tdesign--chevron-down"]}
      aria-hidden="true"
    ></span>
  </BitsSelect.Trigger>
  <BitsSelect.Portal>
    <BitsSelect.Content
      sideOffset={4}
      forceMount
      class={["z-50 text-text", iconOnly ? "w-max min-w-32" : "w-(--bits-select-anchor-width)"]}
      align="end"
    >
      {#snippet child({ props, wrapperProps, open })}
        {#if open}
          <div {...wrapperProps}>
            <div {...props} transition:fly={{ y: -8, duration: "short" }}>
              <HardShadow>
                <BitsSelect.Viewport
                  class={[
                    "max-h-(--bits-select-content-available-height) overflow-y-auto p-1",
                    "bb-border bg-surface",
                  ]}
                >
                  {#each options as option (option.value)}
                    <BitsSelect.Item
                      value={option.value}
                      label={option.label}
                      disabled={option.disabled}
                      class={[
                        "flex cursor-pointer items-center justify-between gap-3 px-3 py-2",
                        "rounded-(--bb-border-radius)",
                        "data-disabled:cursor-not-allowed data-disabled:opacity-50",
                        "data-highlighted:bg-bg data-highlighted:outline-2",
                        "data-highlighted:-outline-offset-2 data-highlighted:outline-line",
                      ]}
                    >
                      {#if option.icon}
                        <span class="iconify {option.icon} shrink-0" aria-hidden="true"></span>
                      {/if}
                      <span class="flex-1">{option.label}</span>
                      <span
                        class="iconify shrink-0 tdesign--check"
                        class:invisible={value !== option.value}
                        aria-hidden="true"
                      ></span>
                    </BitsSelect.Item>
                  {/each}
                </BitsSelect.Viewport>
              </HardShadow>
            </div>
          </div>
        {/if}
      {/snippet}
    </BitsSelect.Content>
  </BitsSelect.Portal>
</BitsSelect.Root>
