<script lang="ts">
  import { onMount } from "svelte";
  import { prefersReducedMotion } from "svelte/motion";
  import Swiper from "swiper";
  import { A11y } from "swiper/modules";
  import "swiper/css";
  import "swiper/css/a11y";
  import Button from "./Button.svelte";
  import Select from "./Select.svelte";
  import ModelDiagnosticControls from "./ModelDiagnosticControls.svelte";
  import ResultPair from "./ResultPair.svelte";
  import { agents, prompts } from "#lib/experiment-results.js";

  let selectedAgent = $state("luna");
  const agent = $derived(agents.find((agent) => agent.value === selectedAgent)!);
  let activePromptIndex = $state(0);
  let outgoingPromptIndex = $state<number | null>(null);
  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
  let container: HTMLDivElement;
  let swiper = $state<Swiper>();

  onMount(() => {
    const carousel = new Swiper(container, {
      modules: [A11y],
      slidesPerView: 1,
      autoHeight: true,
      loop: true,
      spaceBetween: 24,
      speed: prefersReducedMotion.current ? 0 : 300,
      a11y: {
        slideLabelMessage: "{{index}} of {{slidesLength}}",
        wrapperLiveRegion: false,
      },
      on: {
        // Swiper reorders slides when looping; realIndex still follows the prompt order.
        realIndexChange(instance) {
          outgoingPromptIndex = activePromptIndex;
          activePromptIndex = instance.realIndex;
        },
        slideChangeTransitionEnd() {
          outgoingPromptIndex = null;
        },
      },
    });
    swiper = carousel;
    return () => carousel.destroy(true, true);
  });

  $effect(() => {
    if (swiper) swiper.params.speed = prefersReducedMotion.current ? 0 : 300;
  });
</script>

<section aria-label="Qualitative comparison" aria-roledescription="carousel">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <h3 class="text-2xl">Qualitative comparison</h3>
      <div class="w-48">
        <Select label="Agent model" hideLabel options={agents} bind:value={selectedAgent} />
      </div>
    </div>
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
  </div>
  <div class="swiper min-w-0" bind:this={container}>
    <div class="swiper-wrapper">
      {#each prompts as prompt, index (prompt.id)}
        {@const showModels = index === activePromptIndex || index === outgoingPromptIndex}
        <div
          class="swiper-slide p-1"
          inert={index !== activePromptIndex}
          aria-hidden={index !== activePromptIndex}
        >
          <p class="mb-4 cursor-grab text-sm leading-relaxed text-pretty active:cursor-grabbing">
            <span class="font-semibold">Prompt:</span>
            <span class="italic">“{prompt.caption}”</span>
          </p>
          <!-- Keep the outgoing pair mounted until the slide animation ends. -->
          {#key `${selectedAgent}-${showModels}`}
            <ResultPair {agent} {prompt} {showModels} {showIntersections} {highlightCollisions} />
          {/key}
        </div>
      {/each}
    </div>
  </div>
  <div class="mt-6 flex items-center justify-between gap-3">
    <p class="min-w-0 flex-1 text-sm text-pretty">
      Swipe the prompt or use the arrows to browse. Red lines show mesh intersections. Drag a build
      to rotate it.
    </p>
    <div class="bb-btn-container flex shrink-0 items-center gap-3 pt-1 pl-1">
      <Button
        text="Previous prompt"
        action={() => swiper?.slidePrev()}
        icon="tdesign--chevron-left"
        iconOnly
      />
      <p
        role="status"
        aria-label="Prompt position"
        aria-live="polite"
        aria-atomic="true"
        class="relative -top-1 -left-0.5 min-w-8 text-center tabular-nums"
      >
        {activePromptIndex + 1} / {prompts.length}
      </p>
      <Button
        text="Next prompt"
        action={() => swiper?.slideNext()}
        icon="tdesign--chevron-right"
        iconOnly
      />
    </div>
  </div>
</section>
