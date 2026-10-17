<script lang="ts">
  import { onMount } from "svelte";
  import Select from "./Select.svelte";

  const themes = [
    { value: "auto", label: "Auto", icon: "tdesign--contrast-filled" },
    { value: "light", label: "Light", icon: "tdesign--sunny" },
    { value: "dark", label: "Dark", icon: "tdesign--moon" },
  ];
  let theme = $state("auto");

  onMount(() => {
    const saved = document.documentElement.dataset.theme;
    theme = saved === "light" || saved === "dark" ? saved : "auto";
  });

  function selectTheme(value: string) {
    theme = value;
    if (value === "auto") delete document.documentElement.dataset.theme;
    else document.documentElement.dataset.theme = value;
    try {
      localStorage.setItem("brickwright-theme", value);
    } catch {
      // Theme selection still works when browser storage is unavailable
    }
  }
</script>

<Select label="Theme" options={themes} bind:value={() => theme, selectTheme} hideLabel iconOnly />
