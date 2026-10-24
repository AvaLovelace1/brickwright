<script lang="ts">
  import { Select as BitsSelect } from "bits-ui";
  import HardShadow from "./HardShadow.svelte";
  import { fly } from "#lib/motion.svelte.js";
  import type { ClassValue } from "svelte/elements";

  interface Props {
    label: string;
    options: readonly { value: string; label: string; icon?: string }[];
    value: string;
    labelClass?: ClassValue;
    class?: ClassValue;
  }

  let {
    label,
    options,
    value = $bindable(),
    labelClass = "mb-1 text-sm",
    class: className = "",
  }: Props = $props();

  let open = $state(false);
  const uid = $props.id();
  const selectedOption = $derived(options.find((option) => option.value === value));
</script>

<div id="{uid}-label" class={labelClass}>{label}</div>
<BitsSelect.Root type="single" bind:value bind:open allowDeselect={false}>
  <BitsSelect.Trigger
    aria-labelledby="{uid}-label {uid}-value"
    class={[
      "flex w-full cursor-pointer items-center justify-between gap-3 px-3 py-2",
      "bb-border bg-surface",
      "text-left text-text",
      "focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line",
      className,
    ]}
  >
    {#if selectedOption?.icon}
      <span class="iconify {selectedOption.icon} shrink-0" aria-hidden="true"></span>
    {/if}
    <span id="{uid}-value" class="flex-1">{selectedOption?.label}</span>
    <span
      class={["iconify shrink-0", open ? "tdesign--chevron-up" : "tdesign--chevron-down"]}
      aria-hidden="true"
    ></span>
  </BitsSelect.Trigger>
  <BitsSelect.Portal>
    <BitsSelect.Content
      sideOffset={4}
      forceMount
      class="z-100 w-(--bits-select-anchor-width) text-text"
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
                      class={[
                        "flex cursor-pointer items-center justify-between gap-3 px-3 py-2",
                        "rounded-(--bb-border-radius)",
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
