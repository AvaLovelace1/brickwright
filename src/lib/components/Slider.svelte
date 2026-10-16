<script lang="ts">
  import { Slider } from "bits-ui";
  import Tooltip from "$lib/components/Tooltip.svelte";
  import { Tooltip as BitsTooltip } from "bits-ui";

  export interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    step?: number;
    hideLabel?: boolean;
    fmtValue?: (value: number) => string;
  }
  let {
    label,
    value = $bindable(),
    min,
    max,
    step = 1,
    hideLabel = false,
    fmtValue = (value) => value.toString(),
  }: Props = $props();

  const uid = $props.id();
  let showTooltip = $state(false);
  let tooltipAnchor = $state<HTMLElement | null>(null);
</script>

<BitsTooltip.Provider>
  <div class={["mb-1 text-sm", hideLabel && "sr-only"]} id="{uid}-label">{label}</div>
  <Slider.Root
    type="single"
    bind:value
    class="relative flex w-full touch-none items-center select-none"
    {min}
    {max}
    {step}
  >
    <span
      class="relative h-1 w-full grow cursor-pointer overflow-hidden rounded-(--bb-border-radius) bg-line/50"
    >
      <Slider.Range class="absolute h-full bg-line" />
    </span>
    <Slider.Thumb
      class="size-4 cursor-pointer rounded-(--bb-border-radius) bg-primary
           bg-radial from-primary-bright from-35% to-transparent to-36%
           outline-primary focus-visible:outline-2 focus-visible:outline-offset-3"
      index={0}
      aria-labelledby="{uid}-label"
      onfocus={() => (showTooltip = true)}
      onblur={() => (showTooltip = false)}
      bind:ref={tooltipAnchor}
    />
  </Slider.Root>

  <Tooltip side="top" anchor={showTooltip ? tooltipAnchor : null}>
    {#snippet tooltipContent()}{fmtValue(value)}{/snippet}
  </Tooltip>
</BitsTooltip.Provider>
