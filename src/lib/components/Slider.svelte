<script lang="ts">
  import { Slider, Tooltip as BitsTooltip } from "bits-ui";
  import Tooltip from "./Tooltip.svelte";

  interface Props {
    label: string;
    value: number;
    min: number;
    max: number;
    formatValue: (value: number) => string;
  }
  let { label, value = $bindable(), min, max, formatValue }: Props = $props();

  let thumb = $state<HTMLElement | null>(null);
  let thumbFocused = $state(false);
</script>

<!-- Its own provider keeps the value tooltip open while neighbouring tooltips open and close. -->
<BitsTooltip.Provider>
  <Slider.Root
    type="single"
    bind:value
    class="relative flex w-full touch-none items-center select-none"
    {min}
    {max}
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
      aria-label={label}
      aria-valuetext={formatValue(value)}
      onfocus={() => (thumbFocused = true)}
      onblur={() => (thumbFocused = false)}
      bind:ref={thumb}
    />
  </Slider.Root>

  <Tooltip anchor={thumbFocused ? thumb : null}>
    {#snippet tooltipContent()}{formatValue(value)}{/snippet}
  </Tooltip>
</BitsTooltip.Provider>
