<script lang="ts">
  import { resolve } from "$app/paths";
  import BrickWrightLogo from "#lib/components/BrickWrightLogo.svelte";
  import Button from "#lib/components/Button.svelte";
  import ThemeSelect from "#lib/components/ThemeSelect.svelte";
</script>

<header
  class="fixed top-0 z-50 flex w-full items-center gap-2 border-b-4 border-primary bg-surface px-4 py-2 sm:px-8"
>
  <a class="text-4xl sm:text-3xl" href={resolve("/")}>
    <BrickWrightLogo class="max-sm:flex max-sm:[&>img]:mb-0" textClass="sr-only sm:not-sr-only" />
  </a>
  <div class="ml-auto flex gap-2 pt-1">
    <!-- TODO replace with real arxiv link -->
    <Button
      text="Paper"
      action="https://arxiv.org"
      class="bb-btn-primary ms-auto"
      icon="tdesign--file-1"
    />
    <Button
      text="Code"
      action="https://github.com/AvaLovelace1/brickwright"
      icon="tdesign--logo-github"
    />
  </div>
  <ThemeSelect />
</header>
