<script lang="ts">
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
  const playback = $derived(
    playing
      ? { label: "Pause demo", icon: "tdesign--pause" }
      : ended
        ? { label: "Replay demo", icon: "tdesign--refresh" }
        : { label: "Play demo", icon: "tdesign--play" },
  );

  function goToStep(nextIndex: number) {
    playing = false;
    index = nextIndex;
  }

  function togglePlayback() {
    if (ended) index = 0;
    playing = !playing;
  }

  $effect(() => {
    if (!playing || ended) return;
    const nextIndex = index + 1;
    const timer = window.setTimeout(() => {
      index = nextIndex;
      if (ended) playing = false;
    }, STEP_DURATION_MS);
    return () => window.clearTimeout(timer);
  });
</script>

<svelte:document
  onvisibilitychange={() => {
    if (document.hidden) playing = false;
  }}
/>

<figure aria-labelledby="{uid}-title" aria-describedby="{uid}-caption" class="min-w-0">
  <div class="overflow-hidden bb-border bg-bg">
    <h3
      id="{uid}-title"
      class="border-b-2 border-line bg-surface px-4 py-4 font-body text-lg font-semibold sm:px-6"
    >
      BrickWright build creation loop
    </h3>
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
              <Button
                text="Previous step"
                action={() => goToStep(index - 1)}
                icon="tdesign--chevron-left"
                iconOnly
                disabled={index === 0}
              />
              <Button
                text={playback.label}
                action={togglePlayback}
                icon={playback.icon}
                iconOnly
                class="bb-btn-primary"
              />
              <Button
                text="Next step"
                action={() => goToStep(index + 1)}
                icon="tdesign--chevron-right"
                iconOnly
                disabled={ended}
              />
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
                        "h-2 w-full border border-line group-hover:bg-primary-bright group-active:bg-primary-deep",
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
