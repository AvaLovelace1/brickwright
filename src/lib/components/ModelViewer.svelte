<script lang="ts">
  import { onDestroy } from "svelte";
  import { Canvas } from "@threlte/core";
  import LegoModel from "#lib/components/LegoModel.svelte";
  import HardShadow from "#lib/components/HardShadow.svelte";
  import type { ClassValue } from "svelte/elements";
  import { Button, Dialog } from "bits-ui";
  import { fade, scale } from "#lib/motion.svelte.js";
  import Slider from "#lib/components/Slider.svelte";
  import Tooltip from "#lib/components/Tooltip.svelte";
  import { prefersReducedMotion } from "svelte/motion";

  export interface LegoModelView {
    ldr: string;
    ldrPacked: string;
    bricksShown: number;
    maxBricks: number;
    caption: string;
    window?: HTMLElement;
    loaded?: boolean;
  }

  export interface Props {
    model: LegoModelView;
    autoplay?: boolean;
    class?: ClassValue;
  }
  let { model = $bindable(), autoplay = false, class: className = "" }: Props = $props();
  const uid = $props.id();
  const slug = $derived(model.ldr.split("/").pop()?.split(".")[0] ?? "model");

  let tooltipAnchor = $state<HTMLElement | null>(null);
  let currentTool = $state<number | null>(null);
  let popupContent: HTMLElement | null = $state(null);

  let paused = $state(true);
  let expanded = $state(false);
  const ended = $derived(model.bricksShown >= model.maxBricks);
  let autoplayed = false;
  let playInterval: NodeJS.Timeout | undefined;

  const playLabel = $derived(ended ? "Rewind" : paused ? "Play" : "Pause");
  const playIcon = $derived(
    ended ? "tdesign--rollback" : paused ? "tdesign--play" : "tdesign--pause",
  );
  const playAction = $derived(ended ? rewind : paused ? play : pause);

  export interface ViewerTool {
    label: string;
    icon: string;
    onclick?: () => void;
    href?: string;
    download?: string;
  }

  const toolsList = $derived([
    { label: "Previous step", icon: "tdesign--previous", onclick: prevStep },
    { label: playLabel, icon: playIcon, onclick: playAction },
    { label: "Next step", icon: "tdesign--next", onclick: nextStep },
    {
      label: "Download LDraw",
      icon: "tdesign--download",
      href: model.ldr,
      download: `${slug}.ldr`,
    },
    { label: "Close view", icon: "tdesign--fullscreen-exit", onclick: () => (expanded = false) },
    { label: "Expand view", icon: "tdesign--fullscreen", onclick: () => (expanded = true) },
  ]);
  const tooltipText = $derived(currentTool === null ? "" : toolsList[currentTool].label);

  function setTooltip(elem: HTMLElement | null, idx: number | null) {
    tooltipAnchor = elem;
    currentTool = idx;
  }

  function prevStep() {
    model.bricksShown = Math.max(1, model.bricksShown - 1);
  }

  function nextStep() {
    model.bricksShown = Math.min(model.maxBricks, model.bricksShown + 1);
  }

  function rewind() {
    model.bricksShown = 1;
  }

  function play() {
    paused = false;
    playInterval = setInterval(() => {
      if (!ended) model.bricksShown += 1;
      else pause();
    }, 10);
  }

  function pause() {
    paused = true;
    clearInterval(playInterval);
  }

  $effect(() => {
    if (autoplay && model.loaded && !prefersReducedMotion.current && !autoplayed) {
      autoplayed = true;
      play();
    }
  });

  onDestroy(() => clearInterval(playInterval));

  // We use outline instead of border so the model doesn't cover the border when zoomed.
  const WINDOW_CLASS = "size-[calc(100%-2px)] rounded-xs bg-surface outline-2 outline-line";
  const BTN_CLASS =
    "flex cursor-pointer items-center text-text hover:text-link " +
    "focus-visible:text-link focus-visible:outline-2 outline-link";
</script>

{#snippet viewerTool(idx: number, { label, icon, onclick, href, download }: ViewerTool)}
  <Button.Root
    class={BTN_CLASS}
    {onclick}
    {href}
    {download}
    onpointerenter={(event: PointerEvent) => setTooltip(event.currentTarget as HTMLElement, idx)}
    onpointerleave={() => setTooltip(null, null)}
    onfocus={(event: FocusEvent) => setTooltip(event.currentTarget as HTMLElement, idx)}
    onblur={() => setTooltip(null, null)}
  >
    <span class="iconify {icon}"></span>
    <span class="sr-only">{label}</span>
  </Button.Root>
{/snippet}

{#snippet viewerTools(isExpandedView: boolean)}
  <div class="absolute right-2 bottom-2 left-2 z-10 flex items-center gap-2 text-text">
    {@render viewerTool(0, toolsList[0])}
    {@render viewerTool(1, toolsList[1])}
    {@render viewerTool(2, toolsList[2])}
    <Slider
      label="Bricks shown"
      min={1}
      max={model.maxBricks}
      bind:value={model.bricksShown}
      hideLabel
      fmtValue={(value) => `Brick ${value}`}
    />
    {@render viewerTool(3, toolsList[3])}
    {#if isExpandedView}
      <Dialog.Close
        class={BTN_CLASS}
        onpointerenter={(event: PointerEvent) => setTooltip(event.currentTarget as HTMLElement, 4)}
        onpointerleave={() => setTooltip(null, null)}
        onfocus={(event: FocusEvent) => setTooltip(event.currentTarget as HTMLElement, 4)}
        onblur={() => setTooltip(null, null)}
      >
        <span class="iconify tdesign--fullscreen-exit"></span>
        <span class="sr-only">Close view</span>
      </Dialog.Close>
    {:else}
      {@render viewerTool(5, toolsList[5])}
    {/if}
  </div>
{/snippet}

<figure class={["relative", className]} aria-labelledby="{uid}-figcaption">
  <HardShadow class="size-full">
    <div class={WINDOW_CLASS} bind:this={model.window}></div>
  </HardShadow>
  {#if model.caption}
    <figcaption
      id="{uid}-figcaption"
      class="bb-badge absolute -top-2 -left-2 z-10 max-w-full bg-bg"
    >
      “{model.caption}”
    </figcaption>
  {/if}
  {@render viewerTools(false)}
</figure>

<Dialog.Root bind:open={expanded}>
  <Dialog.Portal>
    <Dialog.Overlay forceMount>
      {#snippet child({ props, open })}
        {#if open}
          <div
            class="fixed inset-0 z-60 bg-black/50"
            role="presentation"
            in:fade={{ duration: "long" }}
            out:fade={{ duration: "medium" }}
            {...props}
          ></div>
        {/if}
      {/snippet}
    </Dialog.Overlay>
    <Dialog.Content
      forceMount
      interactOutsideBehavior="close"
      bind:ref={popupContent}
      onOpenAutoFocus={(event) => {
        event.preventDefault();
        popupContent?.focus();
      }}
      aria-label="Expanded model view"
    >
      {#snippet child({ props, open })}
        {#if open}
          <div class="fixed inset-0 z-60 flex items-center justify-center">
            <div
              class="aspect-square size-full max-h-144 max-w-xl p-3 sm:max-h-168 sm:max-w-2xl md:max-h-192 md:max-w-3xl"
              {...props}
              in:scale={{ duration: "medium" }}
              out:scale={{ duration: "short" }}
            >
              <HardShadow class="size-full">
                <div class={WINDOW_CLASS}>
                  <Canvas>
                    <LegoModel
                      ldrPacked={model.ldrPacked}
                      bricksShown={model.bricksShown}
                      onload={(maxBricks) => {
                        model.maxBricks = maxBricks;
                        model.loaded = true;
                      }}
                    />
                  </Canvas>
                </div>
                {@render viewerTools(true)}
              </HardShadow>
            </div>
          </div>
        {/if}
      {/snippet}
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>

<Tooltip side="top" anchor={tooltipAnchor} interactOutsideBehavior="ignore">
  {#snippet tooltipContent()}{tooltipText}{/snippet}
</Tooltip>
