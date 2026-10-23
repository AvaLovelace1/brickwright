<script lang="ts">
  import { onMount } from "svelte";
  import { on } from "svelte/events";
  import HardShadow from "#lib/components/HardShadow.svelte";
  import Bullet from "#lib/components/Bullet.svelte";
  import ActionButton from "#lib/components/Button.svelte";
  import Dialog from "#lib/components/Dialog.svelte";
  import type { ClassValue } from "svelte/elements";
  import { Button, Dialog as BitsDialog } from "bits-ui";
  import Slider from "#lib/components/Slider.svelte";
  import Tooltip from "#lib/components/Tooltip.svelte";
  import { prefersReducedMotion } from "svelte/motion";
  import {
    loadDiagnostics,
    isPhysicallyValid,
    type DiagnosticDisplay,
  } from "#lib/model-diagnostics.js";
  import { activeView, type ModelView } from "#lib/models.js";

  export interface ViewerBadge {
    text: string;
    description?: string[];
    tone?: "success" | "danger";
  }

  export interface Props extends Partial<DiagnosticDisplay> {
    model: ModelView;
    autoplay?: boolean;
    showCaption?: boolean;
    showBuildControls?: boolean;
    badge?: ViewerBadge;
    class?: ClassValue;
  }
  let {
    model = $bindable(),
    autoplay = false,
    showCaption = true,
    showBuildControls = true,
    badge: badgeOverride,
    highlightCollisions = false,
    showIntersections = false,
    class: className = "",
  }: Props = $props();
  const badge = $derived<ViewerBadge | undefined>(
    badgeOverride ??
      (model.diagnostics && !model.diagnosticsError
        ? isPhysicallyValid(model.diagnostics)
          ? { text: "Valid", tone: "success" }
          : { text: "Invalid", tone: "danger" }
        : undefined),
  );
  const uid = $props.id();
  const hasCaption = $derived(showCaption && Boolean(model.caption));
  const hasIntersections = $derived(
    showIntersections &&
      !model.diagnosticsError &&
      model.stepsShown >= model.maxSteps &&
      Boolean(model.diagnostics?.intersectionPositions.length),
  );
  const slug = $derived(model.ldr.split("/").pop()?.split(".")[0] ?? "model");

  let popupContent: HTMLElement | null = $state(null);

  let paused = $state(true);
  const ended = $derived(model.stepsShown >= model.maxSteps);
  let initialized = false;

  const playLabel = $derived(ended ? "Rewind" : paused ? "Play" : "Pause");
  const playIcon = $derived(
    ended ? "tdesign--rollback" : paused ? "tdesign--play" : "tdesign--pause",
  );

  type ToolName = "previous" | "playback" | "next" | "download" | "close" | "expand";

  interface ViewerTool {
    label: string;
    icon: string;
    onclick?: () => void;
    href?: string;
    download?: string;
  }

  const tools: Record<ToolName, ViewerTool> = $derived({
    previous: {
      label: "Previous step",
      icon: "tdesign--previous",
      onclick: () => (model.stepsShown = Math.max(1, model.stepsShown - 1)),
    },
    playback: { label: playLabel, icon: playIcon, onclick: togglePlayback },
    next: {
      label: "Next step",
      icon: "tdesign--next",
      onclick: () => (model.stepsShown = Math.min(model.maxSteps, model.stepsShown + 1)),
    },
    download: {
      label: "Download LDraw",
      icon: "tdesign--download",
      href: model.ldr,
      download: `${slug}.ldr`,
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
  });
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

  onMount(() =>
    on(window.matchMedia("(prefers-reduced-motion: reduce)"), "change", (event) => {
      if (event.matches) paused = true;
    }),
  );

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
    if (!model.diagnosticsUrl || model.diagnostics) return;
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

  // We use outline instead of border so the model doesn't cover the border when zoomed.
  const WINDOW_CLASS =
    "size-[calc(100%-2px)] rounded-(--bb-border-radius) bg-surface outline-2 outline-line";
  const OVERLAY_CLASS = "pointer-events-none absolute top-1 right-2 left-1 z-10";
  const BTN_CLASS =
    "flex min-h-6 min-w-6 cursor-pointer items-center justify-center text-text hover:text-link " +
    "focus-visible:text-link focus-visible:outline-2 outline-link";
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

{#snippet statusBadge()}
  {#if badge || model.diagnosticsError}
    <div class="pointer-events-none flex flex-wrap items-center gap-x-3 gap-y-1 p-1 text-text">
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
{/snippet}

{#snippet viewerTool(name: ToolName)}
  {@const { label, icon, onclick, href, download } = tools[name]}
  <Tooltip {onclick} type={href ? undefined : "button"} interactOutsideBehavior="ignore">
    {#snippet child({ props })}
      <Button.Root {...props} class={BTN_CLASS} {href} {download}>
        <span class="iconify text-xl {icon}" aria-hidden="true"></span>
        <span class="sr-only">{label}</span>
      </Button.Root>
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
      <ActionButton text="Retry model" action={() => (model.status = "loading")} />
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

{#snippet viewerTools(isExpandedView: boolean)}
  <div
    class="absolute right-2 bottom-2 left-2 z-10 flex items-center justify-end gap-1 text-text @min-[240px]:gap-2"
  >
    {#if model.status === "loaded" && showBuildControls && model.maxSteps > 1}
      <span class="hidden @min-[240px]:contents">{@render viewerTool("previous")}</span>
      {@render viewerTool("playback")}
      <span class="hidden @min-[240px]:contents">{@render viewerTool("next")}</span>
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
  {@attach trackViewport}
  aria-busy={model.status === "idle" || model.status === "loading"}
  class={["@container relative", className]}
  aria-labelledby={hasCaption ? `${uid}-figcaption` : undefined}
  aria-label={!hasCaption ? model.caption : undefined}
>
  <HardShadow class="size-full">
    <div class={WINDOW_CLASS} bind:this={model.window}></div>
  </HardShadow>
  {@render loadStatus()}
  {#if hasCaption}
    <figcaption id="{uid}-figcaption" class={[OVERLAY_CLASS, "flex flex-col gap-2"]}>
      <span class="bb-badge relative -top-3 -left-3 -mb-3 w-fit max-w-full bg-bg">
        “{model.caption}”
      </span>
      {@render statusBadge()}
    </figcaption>
  {:else if badge || model.diagnosticsError}
    <div class={OVERLAY_CLASS}>{@render statusBadge()}</div>
  {/if}
  {@render viewerTools(false)}
</figure>

<BitsDialog.Root bind:open={() => model.expanded ?? false, (open) => (model.expanded = open)}>
  <Dialog
    class="@container aspect-square size-full max-h-144 max-w-xl sm:max-h-168 sm:max-w-2xl md:max-h-192 md:max-w-3xl"
    bind:ref={popupContent}
    onOpenAutoFocus={(event) => {
      event.preventDefault();
      popupContent?.focus();
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
      {@render viewerTools(true)}
    </HardShadow>
  </Dialog>
</BitsDialog.Root>
