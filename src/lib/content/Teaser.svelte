<script lang="ts">
  import { createModel } from "#lib/viewer/models.js";
  import Select from "#lib/components/Select.svelte";
  import ModelViewer from "#lib/viewer/ModelViewer.svelte";
  import SpeechBubble from "#lib/components/SpeechBubble.svelte";
  import ExternalLink from "#lib/components/ExternalLink.svelte";
  import { FEASIBILITY_CHECKS } from "#lib/viewer/model-diagnostics.js";

  import starryNightImage from "#lib/assets/models/teaser/starry-night-reference.jpg";
  import combineHarvesterImage from "#lib/assets/models/teaser/combine-harvester-reference.png";
  import spaceNeedleImage from "#lib/assets/models/teaser/space-needle-reference.jpg";
  import houseImage from "#lib/assets/models/teaser/house-reference.png";
  import foxImage from "#lib/assets/models/teaser/fox-reference.png";
  import flowerPotImage from "#lib/assets/models/teaser/flower-pot-reference.png";

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
        src: starryNightImage,
        alt: "Van Gogh’s The Starry Night: swirling blue sky, crescent moon, dark cypress, and a village",
        width: 1280,
        height: 1014,
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
        src: combineHarvesterImage,
        alt: "Green combine harvester with yellow wheels and a wide cutting header in a field",
        width: 460,
        height: 269,
      },
    },
    {
      label: "Seattle’s Space Needle",
      model: "teaser/space-needle",
      text: "Seattle’s Space Needle, with tapered legs, a saucer observation deck, and its slender spire.",
      image: {
        src: spaceNeedleImage,
        alt: "Seattle’s Space Needle against a clear sky, with the city behind it",
        width: 1280,
        height: 2523,
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
        src: houseImage,
        alt: "Red wooden house with white trim, a columned porch, a balcony, and a dark tiled roof",
        width: 1260,
        height: 709,
      },
    },
    {
      label: "A fox from an image",
      model: "teaser/fox",
      text: "Match the image as closely as possible.",
      image: {
        src: foxImage,
        alt: "Red fox sitting at the edge of a road",
        width: 390,
        height: 378,
      },
    },
    {
      label: "Potted lavender from an image",
      model: "teaser/flower-pot",
      text: "Match the image as closely as possible.",
      image: {
        src: flowerPotImage,
        alt: "Lavender stems in a square white flower pot",
        width: 500,
        height: 529,
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
          {@const image = prompt.image}
          <a
            href={image.src}
            target="_blank"
            rel="external noopener"
            aria-label="View reference image"
            class="mt-1 block w-fit max-w-full rounded-(--bb-border-radius) focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line active:outline-2 active:outline-offset-3 active:outline-primary"
          >
            <img
              src={image.src}
              alt={image.alt}
              width={image.width}
              height={image.height}
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
