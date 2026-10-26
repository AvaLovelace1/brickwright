<script lang="ts">
  import type { Snippet } from "svelte";
  import { Canvas } from "@threlte/core";
  import BrickWrightLogo from "#lib/components/BrickWrightLogo.svelte";
  import HardShadow from "#lib/components/HardShadow.svelte";
  import SpeechBubble from "#lib/components/SpeechBubble.svelte";
  import VideoThumbnailScene from "./VideoThumbnailScene.svelte";
  import { SUBTITLE } from "#lib/paper.js";
  import { frameAt, type Appearance } from "#lib/video-thumbnail/timeline.js";

  let { time }: { time: number } = $props();
  const frame = $derived(frameAt(time));
  const { user, robot, cards, prompt, title } = $derived(frame);
</script>

{#snippet speechBubble(speaker: "user" | "robot", motion: Appearance, children: Snippet)}
  <SpeechBubble
    {speaker}
    class={[
      "min-h-0 gap-5 [--speaker-anchor:2rem]",
      speaker === "robot" && "flex-1",
      !motion.visible && "invisible",
    ]}
    style="translate: 0 {motion.offset}px; opacity: {motion.opacity}"
    avatarClass="size-9 text-2xl"
    tailClass="before:left-[-0.5rem] before:size-4"
  >
    {@render children()}
  </SpeechBubble>
{/snippet}

{#snippet promptContent()}
  <p class="text-[23px] leading-[1.25] whitespace-nowrap" data-testid="prompt">
    Build
    <span class="relative" style:top="{prompt.offset}px" style:opacity={prompt.opacity}>
      {#each prompt.text.split("*") as part, i (i)}
        {#if i % 2}<em>{part}</em>{:else}{part}{/if}
      {/each}
    </span>
  </p>
{/snippet}

{#snippet resultContent()}
  <div class="flex size-full gap-3">
    <HardShadow class="min-w-0 flex-1">
      <div
        class="relative size-[calc(100%-2px)] overflow-hidden rounded-(--bb-border-radius) bg-surface outline-2 outline-line"
      >
        <Canvas renderMode="manual">
          <VideoThumbnailScene {frame} />
        </Canvas>
      </div>
    </HardShadow>
    <ul class="flex w-40 shrink-0 flex-col justify-center gap-3">
      {#each cards as card (card.text)}
        <li class={[!card.visible && "invisible"]} style:translate="0 {card.offset}px">
          <HardShadow>
            <div
              class="flex gap-1.5 bb-border bg-success-bright px-2 py-1.5 text-[21px] leading-6 font-semibold text-(--bb-ink-deep)"
            >
              <span aria-hidden="true">✓</span>
              <span class="min-w-0">{card.text}</span>
            </div>
          </HardShadow>
        </li>
      {/each}
    </ul>
  </div>
{/snippet}

<!--
  A 2:1 stage: Hugging Face crops paper videos to 7:5 on desktop and to about 2:1 on phones, so
  everything sits inside the 7:5 area both crops keep.
-->
<section
  aria-label="Prompt to brick build"
  class="relative flex h-100 w-200 items-center justify-center overflow-hidden bg-text text-bg"
>
  <div class="flex h-84 w-128 flex-col gap-4">
    {@render speechBubble("user", user, promptContent)}
    {@render speechBubble("robot", robot, resultContent)}
  </div>
  <hgroup
    class={[
      "absolute inset-0 flex flex-col items-center justify-center gap-3 text-center",
      !title.visible && "invisible",
    ]}
    style:translate="0 {title.offset}px"
    style:opacity={title.opacity}
  >
    <h1 class="text-[80px] leading-none"><BrickWrightLogo /></h1>
    <p class="w-112 text-[30px] leading-tight font-semibold text-balance">
      {SUBTITLE.slice(0, title.typed)}<span class="relative" aria-hidden="true"
        >{#if title.caret}<span class="absolute top-[0.1em] left-0.5 h-[1.1em] w-1 bg-primary"
          ></span>{/if}</span
      ><span class="invisible">{SUBTITLE.slice(title.typed)}</span>
    </p>
  </hgroup>
</section>
