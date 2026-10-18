<script lang="ts">
  import { onDestroy, onMount } from "svelte";
  import { Canvas } from "@threlte/core";
  import LegoModel from "#lib/components/LegoModel.svelte";
  import HardShadow from "#lib/components/HardShadow.svelte";
  import type { ClassValue } from "svelte/elements";
  import { Button, Dialog } from "bits-ui";
  import { fade, scale } from "#lib/motion.svelte.js";
  import Slider from "#lib/components/Slider.svelte";
  import Tooltip from "#lib/components/Tooltip.svelte";
  import { prefersReducedMotion } from "svelte/motion";
  import { loadDiagnostics, type ModelDiagnostics } from "#lib/model-diagnostics.js";

  export interface LegoModelView {
    ldr: string;
    ldrPacked: string;
    stepsShown: number;
    maxSteps: number;
    caption: string;
    window?: HTMLElement;
    loaded?: boolean;
    loadRequested?: boolean;
    diagnosticsUrl?: string;
    diagnostics?: ModelDiagnostics;
    diagnosticsError?: boolean;
  }

  export interface ViewerBadge {
    text: string;
    description?: string;
    tone?: "success" | "danger";
  }

  export interface Props {
    model: LegoModelView;
    autoplay?: boolean;
    showCaption?: boolean;
    badge?: ViewerBadge;
    highlightInvalid?: boolean;
    showIntersections?: boolean;
    class?: ClassValue;
  }
  let {
    model = $bindable(),
    autoplay = false,
    showCaption = true,
    badge,
    highlightInvalid = false,
    showIntersections = false,
    class: className = "",
  }: Props = $props();
  const uid = $props.id();
  const hasCaption = $derived(showCaption && Boolean(model.caption));
  const hasIntersections = $derived(
    showIntersections &&
      !model.diagnosticsError &&
      model.stepsShown >= model.maxSteps &&
      Boolean(model.diagnostics?.intersectionPositions.length),
  );
  const slug = $derived(model.ldr.split("/").pop()?.split(".")[0] ?? "model");

  let tooltipAnchor = $state<HTMLElement | null>(null);
  let currentTool = $state<ToolName | null>(null);
  let popupContent: HTMLElement | null = $state(null);

  let paused = $state(true);
  let expanded = $state(false);
  const ended = $derived(model.stepsShown >= model.maxSteps);
  let initialized = false;
  let figure: HTMLElement;
  let playInterval: NodeJS.Timeout | undefined;

  const playLabel = $derived(ended ? "Rewind" : paused ? "Play" : "Pause");
  const playIcon = $derived(
    ended ? "tdesign--rollback" : paused ? "tdesign--play" : "tdesign--pause",
  );
  const playAction = $derived(ended ? rewind : paused ? play : pause);

  type ToolName = "previous" | "playback" | "next" | "download" | "close" | "expand";

  interface ViewerTool {
    label: string;
    icon: string;
    onclick?: () => void;
    href?: string;
    download?: string;
  }

  const tools: Record<ToolName, ViewerTool> = $derived({
    previous: { label: "Previous step", icon: "tdesign--previous", onclick: prevStep },
    playback: { label: playLabel, icon: playIcon, onclick: playAction },
    next: { label: "Next step", icon: "tdesign--next", onclick: nextStep },
    download: {
      label: "Download LDraw",
      icon: "tdesign--download",
      href: model.ldr,
      download: `${slug}.ldr`,
    },
    close: {
      label: "Close view",
      icon: "tdesign--fullscreen-exit",
      onclick: () => (expanded = false),
    },
    expand: { label: "Expand view", icon: "tdesign--fullscreen", onclick: () => (expanded = true) },
  });
  const tooltipText = $derived(currentTool === null ? "" : tools[currentTool].label);

  function setTooltip(elem: HTMLElement | null, tool: ToolName | null) {
    tooltipAnchor = elem;
    currentTool = tool;
  }

  function prevStep() {
    model.stepsShown = Math.max(1, model.stepsShown - 1);
  }

  function nextStep() {
    model.stepsShown = Math.min(model.maxSteps, model.stepsShown + 1);
  }

  function rewind() {
    pause();
    model.stepsShown = 1;
  }

  function play() {
    paused = false;
    playInterval = setInterval(() => {
      if (!ended) model.stepsShown += 1;
      if (ended) pause();
    }, 10);
  }

  function pause() {
    paused = true;
    clearInterval(playInterval);
  }

  $effect(() => {
    if (!model.loaded || initialized) return;
    initialized = true;
    if (autoplay && !prefersReducedMotion.current) {
      model.stepsShown = 1;
      play();
    } else {
      model.stepsShown = model.maxSteps;
    }
  });

  $effect(() => {
    if (!model.loadRequested || !model.diagnosticsUrl || model.diagnostics) return;
    let disposed = false;
    loadDiagnostics(model.diagnosticsUrl).then(
      (data) => {
        if (!disposed) model.diagnostics = data;
      },
      () => {
        if (!disposed) model.diagnosticsError = true;
      },
    );
    return () => {
      disposed = true;
    };
  });

  onMount(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          model.loadRequested = true;
          observer.disconnect();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(figure);
    return () => observer.disconnect();
  });

  onDestroy(() => clearInterval(playInterval));

  // We use outline instead of border so the model doesn't cover the border when zoomed.
  const WINDOW_CLASS = "size-[calc(100%-2px)] rounded-xs bg-surface outline-2 outline-line";
  const OVERLAY_CLASS = "pointer-events-none absolute top-1 right-2 left-1 z-10";
  const BTN_CLASS =
    "flex cursor-pointer items-center text-text hover:text-link " +
    "focus-visible:text-link focus-visible:outline-2 outline-link";
</script>

{#snippet badgeDetail(text: string, showIntersectionLine = false)}
  <span
    class="inline-flex items-center gap-1 rounded-(--bb-border-radius) bg-surface px-1 text-xs sm:text-sm"
  >
    {#if showIntersectionLine}
      <span class="h-0.5 w-3 shrink-0 bg-[#f00]" aria-hidden="true"></span>
    {/if}
    {text}
  </span>
{/snippet}

{#snippet statusBadge()}
  {#if badge}
    <div class="pointer-events-none flex flex-wrap items-center gap-x-3 gap-y-1 p-1 text-text">
      <span
        role="status"
        class={[
          "bb-badge inline-flex items-center gap-1",
          badge.tone === "danger" ? "bb-badge-danger" : "bb-badge-success",
        ]}
      >
        <span
          class={[
            "iconify shrink-0",
            badge.tone === "danger" ? "tdesign--error-triangle" : "tdesign--check-circle",
          ]}
          aria-hidden="true"
        ></span>
        {badge.text}
      </span>
      {#if hasIntersections}
        {@render badgeDetail("Intersections", true)}
      {/if}
      {#if model.diagnosticsError}
        {@render badgeDetail("Diagnostics unavailable")}
      {/if}
      {#if badge.description}
        {@render badgeDetail(badge.description)}
      {/if}
    </div>
  {/if}
{/snippet}

{#snippet viewerTool(name: ToolName)}
  {@const { label, icon, onclick, href, download } = tools[name]}
  <Button.Root
    class={BTN_CLASS}
    {onclick}
    {href}
    {download}
    onpointerenter={(event: PointerEvent) => setTooltip(event.currentTarget as HTMLElement, name)}
    onpointerleave={() => setTooltip(null, null)}
    onfocus={(event: FocusEvent) => setTooltip(event.currentTarget as HTMLElement, name)}
    onblur={() => setTooltip(null, null)}
  >
    <span class="iconify {icon}"></span>
    <span class="sr-only">{label}</span>
  </Button.Root>
{/snippet}

{#snippet viewerTools(isExpandedView: boolean)}
  <div class="absolute right-2 bottom-2 left-2 z-10 flex items-center justify-end gap-2 text-text">
    {#if model.loaded}
      {@render viewerTool("previous")}
      {@render viewerTool("playback")}
      {@render viewerTool("next")}
      <Slider
        label="Steps shown"
        min={1}
        max={model.maxSteps}
        bind:value={model.stepsShown}
        hideLabel
        fmtValue={(value) => `Step ${value}`}
      />
    {/if}
    {@render viewerTool("download")}
    {@render viewerTool(isExpandedView ? "close" : "expand")}
  </div>
{/snippet}

<figure
  bind:this={figure}
  class={["relative", className]}
  aria-labelledby={hasCaption ? `${uid}-figcaption` : undefined}
  aria-label={!hasCaption ? model.caption : undefined}
>
  <HardShadow class="size-full">
    <div class={WINDOW_CLASS} bind:this={model.window}></div>
  </HardShadow>
  {#if hasCaption}
    <figcaption id="{uid}-figcaption" class={[OVERLAY_CLASS, "flex flex-col gap-2"]}>
      <span class="bb-badge relative -top-3 -left-3 -mb-3 w-fit max-w-full bg-bg">
        “{model.caption}”
      </span>
      {@render statusBadge()}
    </figcaption>
  {:else if badge}
    <div class={OVERLAY_CLASS}>{@render statusBadge()}</div>
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
                      {model}
                      {highlightInvalid}
                      {showIntersections}
                      onload={(maxSteps) => {
                        model.maxSteps = maxSteps;
                        model.loaded = true;
                      }}
                      ondiagnosticerror={() => (model.diagnosticsError = true)}
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
