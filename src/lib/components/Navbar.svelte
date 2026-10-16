<script lang="ts">
  import type { Pathname } from "$app/types";
  import { resolve } from "$app/paths";
  import HardShadow from "$lib/components/HardShadow.svelte";

  interface NavItem {
    label: string;
    href: Pathname;
  }
  interface Props {
    items: NavItem[];
    current: string;
  }
  const { items, current }: Props = $props();

  const formatNum = (num: number) => num.toLocaleString("en-US", { minimumIntegerDigits: 2 });
</script>

<nav class="h-full bg-surface px-4 py-3 sm:px-8 md:px-4">
  <menu class="sticky top-20 flex gap-2 md:flex-col">
    {#each items as { label, href }, i (label)}
      {@const hrefResolved = resolve(href)}
      {@const isCurrent = hrefResolved === current}
      <li>
        <HardShadow bgClass={isCurrent ? "bg-primary-deep" : "bg-transparent"}>
          <a
            class={[
              "flex cursor-pointer items-center gap-1 bb-border px-3 py-2",
              isCurrent && "bg-primary text-ink",
              !isCurrent && "border-transparent hover:border-line hover:bg-bg",
            ]}
            href={hrefResolved}
            aria-current={isCurrent ? "page" : undefined}
          >
            <span class="font-mono text-xs">{formatNum(i + 1)}</span>
            <span class="sr-only font-semibold md:not-sr-only">{label}</span>
          </a>
        </HardShadow>
      </li>
    {/each}
  </menu>
</nav>
