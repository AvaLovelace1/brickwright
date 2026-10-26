<script lang="ts">
  import { prefersReducedMotion } from "svelte/motion";
  import { fly } from "svelte/transition";
  import { stageColors, systemMessage, type DemoStep } from "#lib/content/method.js";
  import HardShadow from "#lib/components/HardShadow.svelte";
  import draft2Render from "#lib/assets/models/method/house-draft2.webp";
  import finalRender from "#lib/assets/models/method/house-final.webp";

  const renders = {
    draft2: {
      src: draft2Render,
      alt: "BrickWright render of the twenty-part house with an off-center brown door",
    },
    final: {
      src: finalRender,
      alt: "BrickWright render of the twenty-part house with a centered brown door",
    },
  };
  const speakers = {
    System: { icon: "tdesign--setting", bubble: "bg-primary-bright text-ink" },
    User: { icon: "tdesign--user", bubble: "bg-secondary-bright text-ink" },
    Agent: { icon: "tdesign--robot", bubble: "bg-surface" },
  };

  let { messages, playing }: { messages: readonly DemoStep[]; playing: boolean } = $props();
  let transcript: HTMLDivElement;
  let transcriptWidth = $state(0);

  $effect(() => {
    // New messages, the thinking indicator, and line wrapping can change the scroll height.
    void [messages, playing, transcriptWidth];
    transcript.scrollTo({ top: transcript.scrollHeight, behavior: "instant" });
  });
</script>

{#snippet resultBadge(label: string, success: boolean)}
  <span
    class={[
      "bb-badge mr-2 px-1 py-0 text-[10px] leading-4",
      success ? "bb-badge-success" : "bb-badge-danger",
    ]}>{label}</span
  >
{/snippet}

<!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard access to the scrollable conversation history.) -->
<div
  bind:this={transcript}
  bind:clientWidth={transcriptWidth}
  role="log"
  aria-label="Mock agent conversation"
  aria-live={playing ? "off" : "polite"}
  tabindex="0"
  class="h-96 overflow-y-auto overscroll-y-contain px-4 py-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-line sm:px-6 lg:h-[32rem]"
>
  <ol class="mx-auto flex max-w-3xl flex-col gap-6 pb-1">
    {#each [systemMessage, ...messages] as message, messageIndex (messageIndex)}
      <li
        in:fly={{
          y: 8,
          opacity: 1,
          duration: message.role === "System" || prefersReducedMotion.current ? 0 : 200,
        }}
        class={message.role === "User" ? "ml-auto max-w-[90%]" : "mr-auto w-full max-w-[94%]"}
      >
        <div class="mb-1 flex items-center gap-2 text-sm">
          <span aria-hidden="true" class={["iconify size-4 shrink-0", speakers[message.role].icon]}
          ></span>
          <span class="font-semibold">{message.role}</span>
          {#if message.role === "System"}<span>({message.annotation})</span>{/if}
        </div>
        <HardShadow>
          <div
            class={["bb-border px-4 py-3 text-sm leading-relaxed", speakers[message.role].bubble]}
          >
            {#each message.text
              .trim()
              .split(/\r?\n\s*\r?\n/) as paragraph, paragraphIndex (paragraphIndex)}
              <p class="mt-3 first:mt-0">
                {#each paragraph.split("`") as part, partIndex (partIndex)}
                  {#if partIndex % 2}<code class="font-mono">{part}</code>{:else}{part}{/if}
                {/each}
              </p>
            {/each}
            {#if message.call}<div
                class="mt-3 border-t-2 border-line pt-3 font-mono text-xs leading-relaxed break-words"
              >
                <span class="mr-1 iconify align-middle tdesign--tools" aria-hidden="true"
                ></span><code>{message.call}</code>
              </div>{/if}
          </div>
        </HardShadow>
        {#if message.result}
          <div
            role="group"
            aria-label="Tool result"
            style:--stage-color={stageColors[message.stage]}
            class="mt-3 ml-3 border-l-4 border-(--stage-color) pl-3"
          >
            {#if message.result.kind === "text"}
              <p class="text-xs leading-loose whitespace-pre-line">{message.result.text}</p>
            {:else if message.result.kind === "success"}
              <p class="text-xs leading-loose">
                {@render resultBadge("OK", true)}
                {message.result.text}
              </p>
            {:else if message.result.kind === "validation"}
              <p class="text-xs leading-loose">
                {#each message.result.checks as check (check.label)}
                  <span class="block">
                    {@render resultBadge(check.passed ? "PASS" : "FAIL", check.passed)}
                    {check.label}
                  </span>
                {/each}
              </p>
            {:else if message.result.kind === "render"}
              {@const render = renders[message.result.revision]}
              <figure class="mt-3 w-fit max-w-full bb-border bg-bg">
                <img
                  src={render.src}
                  alt={render.alt}
                  width="512"
                  height="512"
                  class="aspect-square w-48 object-contain"
                />
              </figure>
            {/if}
          </div>
        {/if}
      </li>
    {/each}
  </ol>
  {#if playing}
    <div class="mx-auto mt-6 flex max-w-3xl items-center gap-2 py-2 text-sm font-semibold">
      <span class="flex items-center gap-1" aria-hidden="true">
        {#each ["bg-primary", "bg-secondary", "bg-primary"] as color, i (i)}
          <span
            style:animation-delay="{i * 150}ms"
            class={["size-2 rounded-(--bb-border-radius) motion-safe:animate-bounce", color]}
          ></span>
        {/each}
      </span>
      <span>Agent is thinking…</span>
    </div>
  {/if}
</div>
