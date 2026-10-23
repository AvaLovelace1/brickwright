<script lang="ts">
  import { Dialog as BitsDialog } from "bits-ui";
  import type { Snippet } from "svelte";
  import type { ClassValue } from "svelte/elements";
  import { fade, scale } from "#lib/motion.svelte.js";

  interface Props extends Omit<
    BitsDialog.ContentProps,
    "child" | "children" | "class" | "forceMount"
  > {
    class?: ClassValue;
    children: Snippet;
  }
  let { ref = $bindable(null), class: className, children, ...contentProps }: Props = $props();
</script>

<BitsDialog.Portal>
  <BitsDialog.Overlay forceMount>
    {#snippet child({ props, open })}
      {#if open}
        <div
          class="fixed inset-0 z-60 bg-black/50"
          role="presentation"
          in:fade={{ duration: "medium" }}
          out:fade={{ duration: "short" }}
          {...props}
        ></div>
      {/if}
    {/snippet}
  </BitsDialog.Overlay>
  <BitsDialog.Content forceMount bind:ref {...contentProps}>
    {#snippet child({ props, open })}
      {#if open}
        <div class="fixed inset-0 z-60 flex items-center justify-center">
          <div
            {...props}
            class={["p-3", className]}
            in:scale={{ duration: "medium" }}
            out:scale={{ duration: "short" }}
          >
            {@render children()}
          </div>
        </div>
      {/if}
    {/snippet}
  </BitsDialog.Content>
</BitsDialog.Portal>
