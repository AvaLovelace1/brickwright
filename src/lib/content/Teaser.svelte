<script lang="ts">
  import { createModel } from "#lib/viewer/models.js";
  import Select from "#lib/components/Select.svelte";
  import PromptStepper from "#lib/components/PromptStepper.svelte";
  import ModelViewer from "#lib/viewer/ModelViewer.svelte";
  import SpeechBubble from "#lib/components/SpeechBubble.svelte";
  import ExternalLink from "#lib/components/ExternalLink.svelte";
  import { FEASIBILITY_CHECKS } from "#lib/viewer/model-diagnostics.js";

  import type { Picture } from "@sveltejs/enhanced-img";

  // Reference images by file name: thumbnails resized at build time, and the originals they link to.
  const thumbnails = import.meta.glob<Picture>("../assets/models/teaser/*-reference.*", {
    eager: true,
    import: "default",
    query: { enhanced: true, w: "384;192" },
  });
  const originals = import.meta.glob<string>("../assets/models/teaser/*-reference.*", {
    eager: true,
    import: "default",
  });
  const referencePath = (file: string) => `../assets/models/teaser/${file}`;

  const prompts = [
    {
      label: "A lighthouse besieged by a sea serpent",
      model: "teaser/lighthouse-sea-serpent",
      text: "A lighthouse besieged by a sea serpent.",
    },
    {
      label: "The Starry Night from a painting",
      model: "teaser/starry-night",
      text: "Recreate this painting as a sculptural 3D LEGO scene using varied pieces. No mosaics.",
      image: {
        file: "starry-night-reference.jpg",
        alt: "Van Gogh’s The Starry Night: swirling blue sky, crescent moon, dark cypress, and a village",
        credit: {
          author: "Vincent van Gogh",
          source:
            "https://commons.wikimedia.org/wiki/File:Van_Gogh_-_Starry_Night_-_Google_Art_Project.jpg",
          license: "Public domain",
          licenseUrl: "https://creativecommons.org/publicdomain/mark/1.0/",
        },
      },
    },
    {
      label: "A combine harvester from an image",
      model: "teaser/combine-harvester",
      text: "Match the image as closely as possible.",
      image: {
        file: "combine-harvester-reference.png",
        alt: "Green combine harvester with yellow wheels and a wide cutting header in a field",
      },
    },
    {
      label: "Seattle’s Space Needle",
      model: "teaser/space-needle",
      text: "Seattle’s Space Needle, with tapered legs, a saucer observation deck, and its slender spire.",
      image: {
        file: "space-needle-reference.jpg",
        alt: "Seattle’s Space Needle against a clear sky, with the city behind it",
        credit: {
          author: "Jordon Kalilich",
          source: "https://commons.wikimedia.org/wiki/File:Space_Needle_2011-07-04.jpg",
          license: "CC BY-SA 3.0",
          licenseUrl: "https://creativecommons.org/licenses/by-sa/3.0/",
        },
      },
    },
    {
      label: "A red house from an image",
      model: "teaser/house",
      text: "Match the image as closely as possible.",
      image: {
        file: "house-reference.png",
        alt: "Red wooden house with white trim, a columned porch, a balcony, and a dark tiled roof",
      },
    },
    {
      label: "A fox from an image",
      model: "teaser/fox",
      text: "Match the image as closely as possible.",
      image: {
        file: "fox-reference.png",
        alt: "Red fox sitting at the edge of a road",
      },
    },
    {
      label: "Potted lavender from an image",
      model: "teaser/flower-pot",
      text: "Match the image as closely as possible.",
      image: {
        file: "flower-pot-reference.png",
        alt: "Lavender stems in a square white flower pot",
      },
    },
    {
      label: "Hong Kong’s Victoria Harbour",
      model: "teaser/victoria-harbour",
      text: "Hong Kong’s Victoria Harbour in 10,000+ parts, with dense skyscrapers and a red-sailed junk.",
    },
    {
      label: "A mountainside city",
      model: "teaser/mountainside-city",
      text: "A mountainside city in 15,000+ parts, with terraced houses, winding stairs, bridges, and waterfalls.",
    },
    {
      label: "A cozy ramen bar",
      model: "teaser/ramen-bar",
      text: "A cozy ramen bar interior with an open kitchen and diners.",
    },
    {
      label: "An Arctic observatory",
      model: "teaser/arctic-observatory",
      text: "An Arctic observatory beneath the aurora.",
    },
    {
      label: "A poseable crab",
      model: "teaser/poseable-crab",
      text: "A poseable crab with eight jointed legs, opening claws, and raised eyestalks.",
    },
    {
      label: "An articulated fencer",
      model: "teaser/articulated-fencer",
      text: "An articulated fencer lunging forward with a foil and raised guard.",
    },
  ] as const;
  const options = prompts.map(({ label }, i) => ({ value: String(i), label }));
  let selected = $state("0");
  const index = $derived(Number(selected));
  const prompt = $derived(prompts[index]);
  const step = (offset: number) => {
    selected = String((index + offset + prompts.length) % prompts.length);
  };
  const BUBBLE_SIZES = {
    class: "min-w-0 gap-5 [--speaker-anchor:2.75rem] sm:gap-6",
    avatarClass: "size-8 text-xl sm:size-12 sm:text-2xl",
    tailClass: "before:left-[-0.4rem] before:size-[0.8rem]",
  };
  let models = $state(prompts.map(({ label, model }) => createModel(model, label)));
</script>

<section aria-label="Prompt to brick build" class="mb-12 grid gap-6">
  <SpeechBubble speaker="user" {...BUBBLE_SIZES}>
    <div class="grid items-center gap-x-2 gap-y-1 text-base lg:grid-cols-[auto_minmax(0,1fr)_auto]">
      <Select
        label="Help me build…"
        labelClass="font-semibold italic text-lg"
        class="min-w-0"
        {options}
        bind:value={selected}
      />
      <PromptStepper
        class="justify-self-end"
        {index}
        count={prompts.length}
        onprevious={() => step(-1)}
        onnext={() => step(1)}
      />
      <div class="mt-1 min-w-0 lg:col-span-2 lg:col-start-2">
        <p class="text-sm italic">“{prompt.text}”</p>
        {#if "image" in prompt}
          {@const image = prompt.image}
          <a
            href={originals[referencePath(image.file)]}
            target="_blank"
            rel="external noopener"
            aria-label="View reference image"
            class="mt-1 block w-fit max-w-full rounded-(--bb-border-radius) focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line active:outline-2 active:outline-offset-3 active:outline-primary"
          >
            <enhanced:img
              src={thumbnails[referencePath(image.file)]}
              alt={image.alt}
              sizes="12rem"
              class="h-auto max-h-40 w-auto max-w-48 bb-border"
            />
          </a>
          {#if "credit" in image}
            <p
              class="mt-1 text-xs [&_a]:text-link [&_a]:underline [&_a]:hover:text-link-hover [&_a]:focus-visible:outline-2 [&_a]:focus-visible:outline-offset-2 [&_a]:focus-visible:outline-line"
            >
              Image:
              <ExternalLink href={image.credit.source}>{image.credit.author}</ExternalLink>,
              <ExternalLink href={image.credit.licenseUrl}>{image.credit.license}</ExternalLink>
            </p>
          {/if}
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
