<script lang="ts">
  import { createModel } from "#lib/models.js";
  import Select from "#lib/components/Select.svelte";
  import ModelViewer from "#lib/components/ModelViewer.svelte";
  import SpeechBubble from "#lib/components/SpeechBubble.svelte";
  import { FEASIBILITY_CHECKS } from "#lib/model-diagnostics.js";

  import referenceImage from "#lib/assets/models/teaser/combine-harvester-reference.png";

  const prompts = [
    {
      label: "A lighthouse besieged by a sea serpent",
      model: "teaser/lighthouse-sea-serpent",
      text: "A lighthouse besieged by a sea serpent.",
    },
    {
      label: "A combine harvester from an image",
      model: "teaser/combine-harvester",
      text: "Match the image as closely as possible.",
      image: referenceImage,
      imageAlt: "Green combine harvester with yellow wheels and a wide cutting header in a field",
    },
    {
      label: "Hong Kong’s Victoria Harbour",
      model: "teaser/victoria-harbour",
      text: "Hong Kong’s Victoria Harbour in 10,000+ parts, with dense skyscrapers and a red-sailed junk.",
    },
    {
      label: "A poseable crab",
      model: "teaser/poseable-crab",
      text: "A poseable crab with eight jointed legs, opening claws, and raised eyestalks.",
    },
  ] as const;
  const options = prompts.map(({ label }, i) => ({ value: String(i), label }));
  let selected = $state("0");
  const index = $derived(Number(selected));
  const prompt = $derived(prompts[index]);
  const BUBBLE_SIZES = {
    class: "min-w-0 gap-5 [--speaker-anchor:2.75rem] sm:gap-6",
    avatarClass: "size-8 text-xl sm:size-12 sm:text-2xl",
    tailClass: "before:left-[-0.4rem] before:size-[0.8rem]",
  };
  let models = $state(prompts.map(({ label, model }) => createModel(model, label)));
</script>

<section aria-label="Prompt to brick build" class="mb-12 grid gap-6">
  <SpeechBubble speaker="user" {...BUBBLE_SIZES}>
    <div class="grid items-center gap-x-2 gap-y-1 text-base sm:grid-cols-[auto_minmax(0,1fr)]">
      <Select
        label="Help me build…"
        labelClass="font-semibold italic text-lg"
        class="min-w-0"
        {options}
        bind:value={selected}
      />
      <div class="mt-1 min-w-0 sm:col-start-2">
        <p class="text-sm italic">“{prompt.text}”</p>
        {#if "image" in prompt}
          <a
            href={prompt.image}
            target="_blank"
            rel="external noopener"
            aria-label="View reference image"
            class="mt-1 block w-48 max-w-full rounded-(--bb-border-radius) focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line active:outline-2 active:outline-offset-3 active:outline-primary"
          >
            <img
              src={prompt.image}
              alt={prompt.imageAlt}
              width="460"
              height="269"
              class="h-auto w-full bb-border"
            />
          </a>
        {/if}
      </div>
    </div>
  </SpeechBubble>
  <SpeechBubble speaker="robot" {...BUBBLE_SIZES}>
    {#key selected}
      <ModelViewer
        bind:model={models[index]}
        class="aspect-4/3 sm:aspect-3/2 lg:aspect-video"
        autoplay
        badge={{
          text: "Physically feasible",
          description: FEASIBILITY_CHECKS,
        }}
      />
    {/key}
  </SpeechBubble>
</section>
