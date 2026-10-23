<script lang="ts">
  import { Dialog } from "bits-ui";
  import ThemeSelect from "./ThemeSelect.svelte";
  import Checkbox from "./Checkbox.svelte";
  import { viewerSettings } from "#lib/settings.svelte.js";
  import { fade, scale } from "#lib/motion.svelte.js";

  let trigger = $state<HTMLButtonElement | null>(null);
</script>

<Dialog.Root>
  <Dialog.Trigger
    bind:ref={trigger}
    class="bb-btn flex size-11 items-center justify-center p-2"
    title="Settings"
    aria-label="Settings"
  >
    <span class="iconify text-lg tdesign--setting" aria-hidden="true"></span>
  </Dialog.Trigger>
  <Dialog.Portal>
    <Dialog.Overlay forceMount>
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
    </Dialog.Overlay>
    <Dialog.Content
      forceMount
      onCloseAutoFocus={(event) => {
        event.preventDefault();
        trigger?.focus({ preventScroll: true });
      }}
    >
      {#snippet child({ props, open })}
        {#if open}
          <div class="fixed inset-0 z-60 flex items-center justify-center">
            <div
              {...props}
              class="max-w-sm p-3"
              in:scale={{ duration: "medium" }}
              out:scale={{ duration: "short" }}
            >
              <div class="bb-card">
                <Dialog.Title class="pr-8 font-display text-2xl font-extrabold">
                  Settings
                </Dialog.Title>
                <div class="mt-6 space-y-6">
                  <div><ThemeSelect /></div>
                  <Checkbox
                    label="Automatically rotate models"
                    bind:checked={viewerSettings.rotateModels}
                  />
                </div>
                <Dialog.Close
                  aria-label="Close settings"
                  class="absolute top-2 right-2 flex size-8 cursor-pointer items-center justify-center
                         rounded-(--bb-border-radius) hover:text-link
                         focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line"
                >
                  <span class="iconify text-xl tdesign--close" aria-hidden="true"></span>
                </Dialog.Close>
              </div>
            </div>
          </div>
        {/if}
      {/snippet}
    </Dialog.Content>
  </Dialog.Portal>
</Dialog.Root>
