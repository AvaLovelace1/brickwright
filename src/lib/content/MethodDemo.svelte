<script lang="ts">
  import { onMount } from "svelte";
  import { Button as BitsButton } from "bits-ui";
  import Button from "#lib/components/Button.svelte";
  import Tooltip from "#lib/components/Tooltip.svelte";
  import Bullet from "#lib/components/Bullet.svelte";
  import { demoSteps } from "#lib/method.js";
  import MethodFlowchart from "./MethodFlowchart.svelte";
  import MethodChat from "./MethodChat.svelte";
  import MethodBuildViewer from "./MethodBuildViewer.svelte";

  const uid = $props.id();
  const STEP_DURATION_MS = 4200;
  let index = $state(0);
  let playing = $state(false);
  const step = $derived(demoSteps[index]);
  const ended = $derived(index === demoSteps.length - 1);
  const playLabel = $derived(playing ? "Pause demo" : ended ? "Replay demo" : "Play demo");

  const controls = $derived([
    {
      id: "previous",
      label: "Previous step",
      icon: "tdesign--chevron-left",
      disabled: index === 0,
      onclick: () => goToStep(index - 1),
    },
    {
      id: "playback",
      label: playLabel,
      icon: playing ? "tdesign--pause" : ended ? "tdesign--refresh" : "tdesign--play",
      onclick: togglePlayback,
    },
    {
      id: "next",
      label: "Next step",
      icon: "tdesign--chevron-right",
      disabled: ended,
      onclick: () => goToStep(index + 1),
    },
  ]);

  function goToStep(nextIndex: number) {
    playing = false;
    index = Math.max(0, Math.min(demoSteps.length - 1, nextIndex));
  }

  function togglePlayback() {
    if (ended) index = 0;
    playing = !playing;
  }

  $effect(() => {
    const currentIndex = index;
    if (!playing || currentIndex === demoSteps.length - 1) return;
    const timer = window.setTimeout(() => {
      index = currentIndex + 1;
      if (index === demoSteps.length - 1) playing = false;
    }, STEP_DURATION_MS);
    return () => window.clearTimeout(timer);
  });

  onMount(() => {
    const pauseWhenHidden = () => {
      if (document.hidden) playing = false;
    };
    document.addEventListener("visibilitychange", pauseWhenHidden);
    return () => document.removeEventListener("visibilitychange", pauseWhenHidden);
  });
</script>

<figure aria-labelledby="{uid}-title" aria-describedby="{uid}-caption" class="min-w-0">
  <div class="overflow-hidden bb-border bg-bg">
    <div
      class="flex flex-wrap items-center justify-between gap-2 border-b-2 border-line bg-surface px-4 py-4 sm:px-6"
    >
      <h3 id="{uid}-title" class="font-body text-lg font-semibold">
        BrickWright build creation loop
      </h3>
    </div>
    <div class="grid border-b-2 border-line lg:grid-cols-[minmax(0,3fr)_minmax(0,2fr)]">
      <div class="min-w-0">
        <MethodChat messages={demoSteps.slice(0, index + 1)} {playing} />
        <div class="bb-btn-container border-t-2 border-line bg-surface px-4 py-4 sm:px-6">
          <div class="flex flex-wrap items-center justify-between gap-x-6 gap-y-4">
            <div
              role="group"
              aria-label="Demo playback controls"
              class="flex items-center gap-3 pt-1 pl-1"
            >
              {#each controls as control (control.id)}
                <Button
                  text={control.label}
                  action={control.onclick}
                  icon={control.icon}
                  iconOnly
                  disabled={control.disabled}
                  class={control.id === "playback" ? "bb-btn-primary" : ""}
                />
              {/each}
            </div>
            <p
              role="status"
              aria-label="Demo progress"
              aria-live={playing ? "off" : "polite"}
              aria-atomic="true"
              class="text-sm"
            >
              <span class="font-semibold tabular-nums">Step {index + 1}/{demoSteps.length}</span
              ><Bullet class="mx-1" />{step.title}
            </p>
          </div>
          <div
            class="mt-2 grid grid-cols-6 gap-x-1 sm:grid-cols-11"
            role="group"
            aria-label="Demo steps"
          >
            {#each demoSteps as marker, i (marker)}
              {@const label = `Step ${i + 1}: ${marker.title}`}
              <Tooltip
                type="button"
                aria-label={label}
                onclick={() => goToStep(i)}
                aria-current={i === index ? "step" : undefined}
                class="group flex h-6 min-w-6 cursor-pointer items-center
                       focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line"
              >
                {#snippet child({ props })}
                  <BitsButton.Root {...props}>
                    <span
                      aria-hidden="true"
                      class={[
                        "h-2 w-full border border-line group-hover:bg-primary-bright",
                        i <= index ? "bg-primary" : "bg-bg",
                      ]}
                    ></span>
                  </BitsButton.Root>
                {/snippet}
                {#snippet tooltipContent()}{label}{/snippet}
              </Tooltip>
            {/each}
          </div>
        </div>
      </div>
      <MethodBuildViewer revision={step.revision} />
    </div>
    <MethodFlowchart stage={step.stage} flow={step.flow} />
  </div>
  <figcaption id="{uid}-caption" class="mt-4 text-sm text-pretty">
    <strong>Illustrative demo of brick build generation with BrickWright.</strong>
    This is a scripted conversation with real brick builds, renders, and validation results.
  </figcaption>
</figure>
