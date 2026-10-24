<script lang="ts">
  import { Button as BitsButton, Dialog as BitsDialog } from "bits-ui";
  import { prefersReducedMotion } from "svelte/motion";
  import type { ClassValue } from "svelte/elements";
  import Bullet from "./Bullet.svelte";
  import Button from "./Button.svelte";
  import Dialog from "./Dialog.svelte";
  import HardShadow from "./HardShadow.svelte";
  import Slider from "./Slider.svelte";
  import Tooltip from "./Tooltip.svelte";
  import {
    loadDiagnostics,
    isPhysicallyValid,
    type DiagnosticDisplay,
  } from "#lib/model-diagnostics.js";
  import { activeView, type ModelView } from "#lib/models.js";

  interface ViewerBadge {
    text: string;
    description?: string[];
    tone?: "success" | "danger";
  }

  export interface Props extends Partial<DiagnosticDisplay> {
    model: ModelView;
    autoplay?: boolean;
    showBuildControls?: boolean;
    badge?: ViewerBadge;
    class?: ClassValue;
  }
  let {
    model = $bindable(),
    autoplay = false,
    showBuildControls = true,
    badge: badgeOverride,
    highlightCollisions = false,
    showIntersections = false,
    class: className = "",
  }: Props = $props();
  const badge = $derived<ViewerBadge | undefined>(
    badgeOverride ??
      (model.diagnostics
        ? isPhysicallyValid(model.diagnostics)
          ? { text: "Valid", tone: "success" }
          : { text: "Invalid", tone: "danger" }
        : undefined),
  );
  const ended = $derived(model.stepsShown >= model.maxSteps);
  const hasIntersections = $derived(
    showIntersections && ended && Boolean(model.diagnostics?.intersectionPositions.length),
  );

  let dialogContent: HTMLElement | null = $state(null);
  let paused = $state(true);
  let initialized = false;

  interface ViewerTool {
    label: string;
    icon: string;
    onclick?: () => void;
    href?: string;
    download?: string;
  }

  const tools = $derived({
    previous: {
      label: "Previous step",
      icon: "tdesign--previous",
      onclick: () => (model.stepsShown = Math.max(1, model.stepsShown - 1)),
    },
    playback: {
      ...(ended
        ? { label: "Rewind", icon: "tdesign--rollback" }
        : paused
          ? { label: "Play", icon: "tdesign--play" }
          : { label: "Pause", icon: "tdesign--pause" }),
      onclick: togglePlayback,
    },
    next: {
      label: "Next step",
      icon: "tdesign--next",
      onclick: () => (model.stepsShown = Math.min(model.maxSteps, model.stepsShown + 1)),
    },
    download: {
      label: "Download LDraw",
      icon: "tdesign--download",
      href: model.ldr,
      // Asset URLs carry a content hash: cruise-ship.Ab12Cd.ldr downloads as cruise-ship.ldr.
      download: `${model.ldr.split("/").pop()!.split(".")[0]}.ldr`,
    },
    close: {
      label: "Close view",
      icon: "tdesign--fullscreen-exit",
      onclick: () => (model.expanded = false),
    },
    expand: {
      label: "Expand view",
      icon: "tdesign--fullscreen",
      onclick: () => (model.expanded = true),
    },
  } satisfies Record<string, ViewerTool>);
  function togglePlayback() {
    if (ended) {
      paused = true;
      model.stepsShown = 1;
    } else {
      paused = !paused;
    }
  }

  $effect(() => {
    if (paused || !activeView(model)) return;
    const timer = setInterval(() => {
      if (model.stepsShown < model.maxSteps) model.stepsShown += 1;
      if (model.stepsShown >= model.maxSteps) paused = true;
    }, 10);
    return () => clearInterval(timer);
  });

  $effect(() => {
    if (prefersReducedMotion.current) paused = true;
  });

  $effect(() => {
    if (model.status !== "loaded" || initialized) return;
    initialized = true;
    if (autoplay && !prefersReducedMotion.current) {
      model.stepsShown = 1;
      paused = false;
    } else {
      model.stepsShown = model.maxSteps;
    }
  });

  function requestLoad() {
    if (model.status !== "idle") return;
    model.status = "loading";
    if (!model.diagnosticsUrl) return;
    loadDiagnostics(model.diagnosticsUrl).then(
      (data) => (model.diagnostics = data),
      () => (model.diagnosticsError = true),
    );
  }

  function trackViewport(figure: HTMLElement) {
    const observer = new IntersectionObserver(
      ([entry]) => {
        model.inViewport = entry.isIntersecting;
        if (entry.isIntersecting) requestLoad();
      },
      { rootMargin: "200px" },
    );
    observer.observe(figure);
    return () => observer.disconnect();
  }

  // The outline sits outside the canvas, so a zoomed model can't cover it.
  const WINDOW_CLASS =
    "size-[calc(100%-2px)] rounded-(--bb-border-radius) bg-surface outline-2 outline-line";
</script>

{#snippet badgeDetail(text: string | string[], showIntersectionLine = false)}
  <span
    class="inline-flex items-center gap-1 rounded-(--bb-border-radius) bg-surface px-1 text-xs sm:text-sm"
  >
    {#if showIntersectionLine}
      <span class="h-0.5 w-3 shrink-0 bg-[#f00]" aria-hidden="true"></span>
    {/if}
    <span>
      {#each [text].flat() as item, i (item)}
        {#if i > 0}<Bullet class="mx-1" />{/if}<span>{item}</span>
      {/each}
    </span>
  </span>
{/snippet}

{#snippet toolButton({ label, icon, onclick, href, download }: ViewerTool)}
  <Tooltip {onclick} interactOutsideBehavior="ignore">
    {#snippet child({ props })}
      <BitsButton.Root
        {...props}
        class="flex min-h-6 min-w-6 cursor-pointer items-center justify-center text-text outline-link hover:text-link focus-visible:text-link focus-visible:outline-2"
        {href}
        {download}
      >
        <span class="iconify text-xl {icon}" aria-hidden="true"></span>
        <span class="sr-only">{label}</span>
      </BitsButton.Root>
    {/snippet}
    {#snippet tooltipContent()}{label}{/snippet}
  </Tooltip>
{/snippet}

{#snippet loadStatus()}
  {#if model.status === "error"}
    <div
      class="absolute inset-0 flex flex-col items-center justify-center gap-2 p-4 text-center text-sm text-text"
    >
      <p role="alert">Unable to load the 3D model.</p>
      <Button text="Retry model" action={() => (model.status = "loading")} />
    </div>
  {:else if model.status !== "loaded"}
    <p
      aria-live="polite"
      class="pointer-events-none absolute inset-0 flex items-center justify-center text-sm text-text italic"
    >
      Loading model…
    </p>
  {/if}
{/snippet}

{#snippet toolbar(expanded: boolean)}
  <div
    class="absolute right-2 bottom-2 left-2 z-10 flex items-center justify-end gap-1 text-text @min-[240px]:gap-2"
  >
    {#if model.status === "loaded" && showBuildControls && model.maxSteps > 1}
      <span class="hidden @min-[240px]:contents">{@render toolButton(tools.previous)}</span>
      {@render toolButton(tools.playback)}
      <span class="hidden @min-[240px]:contents">{@render toolButton(tools.next)}</span>
      <Slider
        label="Steps shown"
        min={1}
        max={model.maxSteps}
        bind:value={model.stepsShown}
        formatValue={(value) => `Step ${value}`}
      />
    {/if}
    {@render toolButton(tools.download)}
    {@render toolButton(expanded ? tools.close : tools.expand)}
  </div>
{/snippet}

<figure
  {@attach trackViewport}
  aria-busy={model.status === "idle" || model.status === "loading"}
  class={["@container relative", className]}
  aria-label={model.caption}
>
  <HardShadow class="size-full">
    <div class={WINDOW_CLASS} bind:this={model.window}></div>
  </HardShadow>
  {@render loadStatus()}
  {#if badge || model.diagnosticsError}
    <div
      class="pointer-events-none absolute top-1 right-2 left-1 z-10 flex flex-wrap items-center gap-x-3 gap-y-1 p-1 text-text"
    >
      {#if badge}
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
      {/if}
      {#if hasIntersections}
        {@render badgeDetail("Intersections", true)}
      {/if}
      {#if model.diagnosticsError}
        {@render badgeDetail("Diagnostics unavailable")}
      {/if}
      {#if badge?.description}
        {@render badgeDetail(badge.description)}
      {/if}
    </div>
  {/if}
  {@render toolbar(false)}
</figure>

<BitsDialog.Root bind:open={model.expanded}>
  <Dialog
    class="@container aspect-square size-full max-h-144 max-w-xl sm:max-h-168 sm:max-w-2xl md:max-h-192 md:max-w-3xl"
    bind:ref={dialogContent}
    onOpenAutoFocus={(event) => {
      event.preventDefault();
      dialogContent?.focus();
    }}
    aria-label="Expanded model view"
  >
    <HardShadow class="size-full">
      <div class={WINDOW_CLASS}>
        <svelte:boundary>
          {#await import("./ExpandedModel.svelte") then { default: ExpandedModel }}
            <ExpandedModel {model} {highlightCollisions} {showIntersections} />
          {/await}
          {#snippet failed()}
            <p role="alert" class="p-4 text-text">
              3D viewer unavailable. You can still download the LDraw file.
            </p>
          {/snippet}
        </svelte:boundary>
      </div>
      {@render loadStatus()}
      {@render toolbar(true)}
    </HardShadow>
  </Dialog>
</BitsDialog.Root>
