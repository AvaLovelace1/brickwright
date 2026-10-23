<script lang="ts">
  import type { Snippet } from "svelte";
  import { createModel } from "#lib/models.js";
  import Select from "#lib/components/Select.svelte";
  import ModelViewer from "#lib/components/ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";

  import referenceImage from "#lib/assets/models/teaser/combine-harvester-reference.png";

  const prompts = [
    {
      label: "A lighthouse besieged by a sea serpent",
      filename: "lighthouse-sea-serpent",
      text: "A lighthouse besieged by a sea serpent.",
    },
    {
      label: "A combine harvester from an image",
      filename: "combine-harvester",
      text: "Match the image as closely as possible.",
      image: referenceImage,
      imageAlt: "Green combine harvester with yellow wheels and a wide cutting header in a field",
    },
    {
      label: "Hong Kong’s Victoria Harbour",
      filename: "victoria-harbour",
      text: "Hong Kong’s Victoria Harbour in 10,000+ parts, with dense skyscrapers and a red-sailed junk.",
    },
    {
      label: "A poseable crab",
      filename: "poseable-crab",
      text: "A poseable crab with eight jointed legs, opening claws, and raised eyestalks.",
    },
  ] as const;
  const options = prompts.map(({ label }, i) => ({ value: String(i), label }));
  let selected = $state("0");
  const index = $derived(Number(selected));
  const prompt = $derived(prompts[index]);
  let models = $state(
    prompts.map(({ label, filename }) => createModel(`teaser/${filename}`, label)),
  );
</script>

{#snippet speechBubble(speaker: "user" | "robot", children: Snippet)}
  <div
    class={[
      "flex min-w-0 gap-5 sm:gap-6",
      speaker === "user" ? "items-center" : "items-start [--speaker-anchor:2.75rem]",
    ]}
  >
    <span
      class={[
        "flex size-8 shrink-0 items-center justify-center sm:size-12",
        "bb-border bg-(--bb-ink-bright)",
        speaker === "user"
          ? "border-primary text-primary"
          : "relative top-(--speaker-anchor) -translate-y-1/2 border-secondary text-secondary",
      ]}
      aria-hidden="true"
    >
      <span
        class={[
          "iconify text-xl sm:text-2xl",
          speaker === "user" ? "tdesign--user" : "tdesign--robot",
        ]}
      ></span>
    </span>
    <div
      class={[
        "relative min-w-0 flex-1 p-3",
        "rounded-(--bb-border-radius) bg-bg text-text",
        "before:absolute before:left-[-0.4rem] before:size-[0.8rem]",
        "before:-translate-y-1/2 before:rotate-45 before:bg-bg before:content-['']",
        speaker === "user" ? "before:top-1/2" : "before:top-(--speaker-anchor)",
      ]}
    >
      {@render children()}
    </div>
  </div>
{/snippet}

{#snippet promptContent()}
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
          class="mt-1 block w-48 max-w-full rounded-(--bb-border-radius) focus-visible:outline-2 focus-visible:outline-offset-3 focus-visible:outline-line"
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
{/snippet}

{#snippet resultContent()}
  <div class="relative">
    {#key selected}
      <ModelViewer
        bind:model={models[index]}
        class="aspect-4/3 sm:aspect-3/2 lg:aspect-video"
        autoplay
        showCaption={false}
        badge={{
          text: "Physically feasible",
          description: ["Real LEGO® parts", "No collisions or floaters", "Fully connected"],
        }}
      />
      <SharedCanvas models={[models[index]]} />
    {/key}
  </div>
{/snippet}

<section aria-label="Prompt to brick build" class="mb-12 grid gap-6">
  {@render speechBubble("user", promptContent)}
  {@render speechBubble("robot", resultContent)}
</section>
