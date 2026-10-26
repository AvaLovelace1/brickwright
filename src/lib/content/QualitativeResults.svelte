<script lang="ts">
  import { untrack } from "svelte";
  import { prefersReducedMotion } from "svelte/motion";
  import Swiper from "swiper";
  import { A11y } from "swiper/modules";
  import "swiper/css";
  import "swiper/css/a11y";
  import PromptStepper from "#lib/components/PromptStepper.svelte";
  import Select from "#lib/components/Select.svelte";
  import ModelDiagnosticControls from "#lib/viewer/ModelDiagnosticControls.svelte";
  import ResultPair from "./ResultPair.svelte";
  import { agents, prompts } from "#lib/content/experiment-results.js";

  let selectedAgent = $state("luna");
  const agent = $derived(agents.find((agent) => agent.value === selectedAgent)!);
  let activePromptIndex = $state(0);
  let outgoingPromptIndex = $state<number | null>(null);
  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
  let swiper: Swiper | undefined;

  function carousel(container: HTMLDivElement) {
    const instance = untrack(
      () =>
        new Swiper(container, {
          modules: [A11y],
          slidesPerView: 1,
          autoHeight: true,
          loop: true,
          spaceBetween: 24,
          // Window resizes re-snap the slides. The container's height follows autoHeight, and a
          // re-snap after each height change lands a frame late, undoing a click made in that frame.
          resizeObserver: false,
          // A transform or z-index would stack the slides' viewer controls beneath the page's
          // 3D canvas, so the wrapper moves by its left offset and the classes below unset both.
          virtualTranslate: true,
          a11y: {
            slideLabelMessage: "{{index}} of {{slidesLength}}",
            wrapperLiveRegion: false,
          },
          on: {
            setTranslate({ wrapperEl }, translate) {
              wrapperEl.style.left = `${translate}px`;
            },
            // Swiper reorders slides when looping; realIndex still follows the prompt order.
            realIndexChange({ realIndex }) {
              outgoingPromptIndex = activePromptIndex;
              activePromptIndex = realIndex;
            },
            slideChangeTransitionEnd() {
              outgoingPromptIndex = null;
            },
          },
        }),
    );
    $effect(() => {
      instance.params.speed = prefersReducedMotion.current ? 0 : 300;
    });
    swiper = instance;
    return () => instance.destroy(true, true);
  }
</script>

<section aria-label="Qualitative comparison" aria-roledescription="carousel">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-4">
    <div class="flex flex-wrap items-center gap-x-4 gap-y-2">
      <h3 class="text-2xl">Qualitative comparison</h3>
      <div class="w-48">
        <Select
          label="Agent model"
          labelClass="sr-only"
          options={agents}
          bind:value={selectedAgent}
        />
      </div>
    </div>
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
  </div>
  <div class="swiper z-auto! min-w-0" {@attach carousel}>
    <div class="swiper-wrapper left-0 z-auto! transform-none! [transition-property:left,height]!">
      {#each prompts as prompt, index (prompt.id)}
        <!-- Keep the outgoing pair mounted until the slide animation ends. -->
        {@const showModels = index === activePromptIndex || index === outgoingPromptIndex}
        <div
          class="swiper-slide transform-none! p-1"
          inert={index !== activePromptIndex}
          aria-hidden={index !== activePromptIndex}
        >
          <p class="mb-4 cursor-grab text-sm leading-relaxed text-pretty active:cursor-grabbing">
            <span class="font-semibold">Prompt:</span>
            <span class="italic">“{prompt.caption}”</span>
          </p>
          {#key `${selectedAgent}-${showModels}`}
            <ResultPair {agent} {prompt} {showModels} {showIntersections} {highlightCollisions} />
          {/key}
        </div>
      {/each}
    </div>
  </div>
  <div class="mt-6 flex items-center justify-between gap-3">
    <p class="min-w-0 flex-1 text-sm text-pretty">
      Swipe the prompt or use the arrows to browse. Red lines indicate brick intersections. Drag a
      build to rotate it.
    </p>
    <PromptStepper
      index={activePromptIndex}
      count={prompts.length}
      onprevious={() => swiper?.slidePrev()}
      onnext={() => swiper?.slideNext()}
    />
  </div>
</section>
