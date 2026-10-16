<script lang="ts">
  import brickagentMark from "$lib/assets/logos/brickagent-mark.svg";
  import bricklayerMark from "$lib/assets/logos/bricklayer-mark.svg";
  import brickwrightMark from "$lib/assets/logos/brickwright-mark.svg";
  import type { ClassValue } from "svelte/elements";

  type Variant = "wright" | "layer" | "agent";

  interface Props {
    variant?: Variant;
    class?: ClassValue;
    textClass?: ClassValue;
  }

  const { variant = "wright", class: className = "", textClass = "" }: Props = $props();

  interface Logo {
    alt: string;
    mark: string;
    text: string;
    height: string;
    gap: string;
  }
  const logos: Record<Variant, Logo> = {
    wright: {
      alt: "BrickWright logo",
      mark: brickwrightMark,
      text: "BrickWright",
      height: "h-[0.875em]",
      gap: "gap-[0.125em]",
    },
    layer: {
      alt: "BrickLayer logo",
      mark: bricklayerMark,
      text: "BrickLayer",
      height: "h-[0.75em]",
      gap: "gap-[0.175em]",
    },
    agent: {
      alt: "BrickAgent logo",
      mark: brickagentMark,
      text: "BrickAgent",
      height: "h-[0.75em]",
      gap: "gap-[0.175em]",
    },
  };

  const logo = $derived(logos[variant]);
</script>

<span class={["flex items-center font-display font-extrabold", logo.gap, className]}>
  <img src={logo.mark} alt={logo.alt} class={["mb-[0.125em]", logo.height]} />
  <span class={textClass}>{logo.text}</span>
</span>
