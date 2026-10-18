<script lang="ts">
  import type { Snippet } from "svelte";
  import Select from "./Select.svelte";
  import ModelViewer, { type LegoModelView } from "./ModelViewer.svelte";
  import SharedCanvas from "./SharedCanvas.svelte";
  import ldr from "#lib/assets/ldr/cruise-ship.ldr?url";
  import ldrPacked from "#lib/assets/ldr/cruise-ship.ldr_Packed.mpd?url";

  const prompts = [
    "A detailed LEGO cruise ship",
    "A detailed LEGO giraffe",
    "A city scene with four buildings",
    "model of my dog",
  ];
  const options = prompts.map((label, i) => ({ value: String(i), label }));
  let selected = $state("0");
  const index = $derived(Number(selected));
  let models = $state<LegoModelView[]>(
    prompts.map((caption) => ({ ldr, ldrPacked, caption, maxBricks: 100, bricksShown: 1 })),
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
  <div class="flex flex-col items-stretch gap-1 text-base sm:flex-row sm:items-center sm:gap-2">
    <Select
      label="Help me design…"
      labelClass="shrink-0 font-semibold italic text-lg"
      class="min-w-0 flex-1"
      {options}
      bind:value={selected}
    />
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
          description:
            "Real LEGO® parts · No intersecting or floating parts · One connected component",
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
