<script lang="ts">
  import { Dialog as BitsDialog } from "bits-ui";
  import ThemeSelect from "./ThemeSelect.svelte";
  import Checkbox from "./Checkbox.svelte";
  import Dialog from "./Dialog.svelte";
  import { viewerSettings } from "#lib/settings.svelte.js";

  let trigger = $state<HTMLButtonElement | null>(null);
</script>

<BitsDialog.Root>
  <BitsDialog.Trigger
    bind:ref={trigger}
    class="bb-btn flex size-11 items-center justify-center p-2"
    title="Settings"
    aria-label="Settings"
  >
    <span class="iconify text-lg tdesign--setting" aria-hidden="true"></span>
  </BitsDialog.Trigger>
  <Dialog
    class="max-w-sm"
    onCloseAutoFocus={(event) => {
      event.preventDefault();
      trigger?.focus({ preventScroll: true });
    }}
  >
    <div class="bb-card">
      <BitsDialog.Title class="pr-8 font-display text-2xl font-extrabold">Settings</BitsDialog.Title
      >
      <div class="mt-6 space-y-6">
        <div><ThemeSelect /></div>
        <Checkbox label="Automatically rotate models" bind:checked={viewerSettings.rotateModels} />
      </div>
      <BitsDialog.Close
        aria-label="Close settings"
        class="absolute top-2 right-2 flex size-8 cursor-pointer items-center justify-center
               rounded-(--bb-border-radius) hover:text-link
               focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line"
      >
        <span class="iconify text-xl tdesign--close" aria-hidden="true"></span>
      </BitsDialog.Close>
    </div>
  </Dialog>
</BitsDialog.Root>
