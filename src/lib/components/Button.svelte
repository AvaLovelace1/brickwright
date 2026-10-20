<script lang="ts">
  import type { PathnameWithSearchOrHash, RouteIdWithSearchOrHash } from "$app/types";
  import { resolve } from "$app/paths";
  import type { ClassValue } from "svelte/elements";
  import { Button } from "bits-ui";
  import Tooltip from "./Tooltip.svelte";

  interface Props {
    text: string;
    action: string | (() => void);
    icon?: string;
    iconOnly?: boolean;
    disabled?: boolean;
    class?: ClassValue;
  }
  let {
    text,
    action,
    icon = "",
    iconOnly = false,
    disabled = false,
    class: className = "",
  }: Props = $props();

  const isInternalLink = (
    href: string,
  ): href is PathnameWithSearchOrHash | RouteIdWithSearchOrHash => !/^https?:\/\//.test(href);

  const onclick = $derived(typeof action === "function" ? action : undefined);
  const actionProps = $derived(
    typeof action === "function"
      ? { type: "button" as const }
      : isInternalLink(action)
        ? { href: resolve(action) }
        : { href: action, target: "_blank", rel: "external noopener" },
  );
</script>

{#snippet content()}
  <div class="flex items-center gap-1">
    {#if icon}<span class={["iconify", icon, iconOnly && "text-lg"]} aria-hidden="true"></span>{/if}
    <span class:sr-only={iconOnly}>{text}</span>
  </div>
{/snippet}

{#snippet button(triggerProps: Record<string, unknown>)}
  <Button.Root
    {...triggerProps}
    {...actionProps}
    class={["bb-btn", iconOnly && "p-2", className]}
    {disabled}
  >
    {@render content()}
  </Button.Root>
{/snippet}

{#if iconOnly}
  <Tooltip {disabled} {onclick}>
    {#snippet child({ props })}{@render button(props)}{/snippet}
    {#snippet tooltipContent()}{text}{/snippet}
  </Tooltip>
{:else}
  {@render button({ onclick })}
{/if}
