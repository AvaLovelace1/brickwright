<script lang="ts">
  import { Tooltip } from "bits-ui";
  import { fly } from "#lib/motion.svelte.js";
  import type { Snippet } from "svelte";

  export interface Props extends Tooltip.TriggerProps {
    tooltipContent: Snippet;
    side?: "top" | "right" | "bottom" | "left";
    anchor?: HTMLElement | null;
    interactOutsideBehavior?: "close" | "ignore";
  }

  const {
    children,
    tooltipContent,
    side = "top",
    anchor,
    interactOutsideBehavior = "close",
    ...triggerProps
  }: Props = $props();

  const anchored = $derived(anchor !== undefined);
  const flyAmount = 4;
  const flyTransition = $derived({
    x: side === "left" ? flyAmount : side === "right" ? -flyAmount : 0,
    y: side === "top" ? flyAmount : side === "bottom" ? -flyAmount : 0,
    duration: "short",
  } as const);
</script>

{#snippet content()}
  <Tooltip.Portal>
    <Tooltip.Content
      role="tooltip"
      {side}
      sideOffset={4}
      customAnchor={anchor}
      forceMount
      {interactOutsideBehavior}
    >
      {#snippet child({ wrapperProps, props, open })}
        {#if open}
          <!-- Set `z-index` so the tooltip appears in front of dialogs.
          Override it inline, since a class would lose to bits-ui's inline style. -->
          <div {...wrapperProps} style="{wrapperProps.style}; z-index: 100">
            <div transition:fly={flyTransition}>
              <div class="bb-border bg-surface px-2 py-1 text-center text-sm text-text" {...props}>
                {@render tooltipContent()}
              </div>
              <Tooltip.Arrow class="text-text" />
            </div>
          </div>
        {/if}
      {/snippet}
    </Tooltip.Content>
  </Tooltip.Portal>
{/snippet}

{#if anchored}
  <Tooltip.Root open={anchor !== null}>
    {@render content()}
  </Tooltip.Root>
{:else}
  <Tooltip.Root>
    <Tooltip.Trigger {...triggerProps}>{@render children?.()}</Tooltip.Trigger>
    {@render content()}
  </Tooltip.Root>
{/if}
