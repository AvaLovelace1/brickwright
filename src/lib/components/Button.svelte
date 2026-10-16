<script lang="ts">
  import type { Pathname } from "$app/types";
  import { resolve } from "$app/paths";
  import type { ClassValue } from "svelte/elements";
  import { Button } from "bits-ui";

  interface Props {
    text: string;
    action: Pathname | string | (() => void);
    icon?: string;
    class?: ClassValue;
  }
  let { text, action, icon = "", class: className = "" }: Props = $props();

  const isInternalLink = (href: string): href is Pathname => !/^https?:\/\//.test(href);

  const BUTTON_CLASSES = "bb-btn";
</script>

{#snippet content()}
  <div class="flex items-center gap-1">
    {#if icon}<span class="iconify {icon}" aria-hidden="true"></span>{/if}
    {text}
  </div>
{/snippet}

{#if typeof action === "string"}
  {#if isInternalLink(action)}
    <Button.Root class={[BUTTON_CLASSES, className]} href={resolve(action)}>
      {@render content()}
    </Button.Root>
  {:else}
    <Button.Root
      class={[BUTTON_CLASSES, className]}
      href={action}
      target="_blank"
      rel="external noopener"
    >
      {@render content()}
    </Button.Root>
  {/if}
{:else}
  <Button.Root class={[BUTTON_CLASSES, className]} type="button" onclick={action}>
    {@render content()}
  </Button.Root>
{/if}
