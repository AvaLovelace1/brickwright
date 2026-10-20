<script lang="ts">
  import brickagentMark from "#lib/assets/logos/brickagent-mark.svg";
  import bricklayerMark from "#lib/assets/logos/bricklayer-mark.svg";
  import brickwrightMark from "#lib/assets/logos/brickwright-mark.svg";
  import type { ClassValue } from "svelte/elements";

  interface Props {
    variant?: keyof typeof logos;
    class?: ClassValue;
    textClass?: ClassValue;
  }

  const { variant = "wright", class: className = "", textClass = "" }: Props = $props();

  const logos = {
    wright: {
      mark: brickwrightMark,
      text: "BrickWright",
      height: "h-[0.875em]",
      gap: "gap-[0.125em]",
    },
    layer: {
      mark: bricklayerMark,
      text: "BrickLayer",
      height: "h-[0.75em]",
      gap: "gap-[0.175em]",
    },
    agent: {
      mark: brickagentMark,
      text: "BrickAgent",
      height: "h-[0.75em]",
      gap: "gap-[0.175em]",
    },
  };

  const logo = $derived(logos[variant]);
</script>

<span class={["inline-flex items-center font-display font-extrabold", logo.gap, className]}>
  <img src={logo.mark} alt="{logo.text} logo" class={["mb-[0.125em]", logo.height]} />
  <span class={["self-baseline", textClass]}>{logo.text}</span>
</span>
