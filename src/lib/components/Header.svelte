<script lang="ts">
  import { resolve } from "$app/paths";
  import BrickWrightLogo from "./BrickWrightLogo.svelte";
  import Button from "./Button.svelte";
  import SettingsDialog from "./SettingsDialog.svelte";
</script>

<header
  class="fixed top-0 z-50 flex w-full items-center gap-2 border-b-4 border-primary bg-surface px-2 py-2 min-[360px]:px-4 sm:px-8"
>
  <a class="shrink-0 text-4xl sm:text-3xl" href={resolve("/")}>
    <BrickWrightLogo class="max-sm:flex max-sm:[&>img]:mb-0" textClass="sr-only sm:not-sr-only" />
  </a>
  <div class="ml-auto flex gap-2 pt-1">
    <Button
      text="Paper"
      action="https://arxiv.org/abs/2610.31651"
      class="bb-btn-primary max-[360px]:px-3"
      icon="tdesign--file-1"
    />
    <Button
      text="Code"
      action="https://github.com/AvaLovelace1/brickwright"
      icon="tdesign--logo-github"
      class="max-[360px]:px-3"
    />
    <SettingsDialog />
  </div>
</header>
