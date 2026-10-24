<script lang="ts">
  import { Tooltip } from "bits-ui";
  import { fly } from "#lib/motion.svelte.js";
  import type { Snippet } from "svelte";

  export interface Props extends Tooltip.TriggerProps {
    tooltipContent: Snippet;
    anchor?: HTMLElement | null;
    interactOutsideBehavior?: "close" | "ignore";
  }

  const {
    children,
    tooltipContent,
    anchor,
    interactOutsideBehavior = "close",
    ...triggerProps
  }: Props = $props();
</script>

{#snippet content()}
  <Tooltip.Portal>
    <Tooltip.Content
      role="tooltip"
      sideOffset={4}
      customAnchor={anchor}
      forceMount
      {interactOutsideBehavior}
    >
      {#snippet child({ wrapperProps, props, open })}
        {#if open}
          <!-- An inline z-index outranks bits-ui's inline style and lifts the tooltip above dialogs. -->
          <div {...wrapperProps} style="{wrapperProps.style}; z-index: 100">
            <div transition:fly={{ y: 4, duration: "short" }}>
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

{#if anchor !== undefined}
  <Tooltip.Root open={anchor !== null}>
    {@render content()}
  </Tooltip.Root>
{:else}
  <Tooltip.Root>
    <Tooltip.Trigger {...triggerProps}>{@render children?.()}</Tooltip.Trigger>
    {@render content()}
  </Tooltip.Root>
{/if}
