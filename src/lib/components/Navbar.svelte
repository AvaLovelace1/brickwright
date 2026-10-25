<script lang="ts">
  import { resolve } from "$app/paths";
  import HardShadow from "./HardShadow.svelte";

  interface NavItem {
    label: string;
    href: `#${string}`;
  }
  interface Props {
    items: NavItem[];
    current: string;
  }
  const { items, current }: Props = $props();
</script>

<nav class="h-full bg-surface px-4 py-3 sm:px-8 md:px-4">
  <menu class="sticky top-20 flex gap-2 md:flex-col">
    {#each items as { label, href }, i (label)}
      {@const isCurrent = href === current}
      <li>
        <HardShadow bgClass={isCurrent ? "bg-primary-deep" : "bg-transparent"}>
          <a
            class={[
              "flex items-center gap-1 bb-border px-3 py-2 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-line",
              isCurrent
                ? "bg-primary text-ink"
                : "border-transparent hover:border-line hover:bg-bg active:border-line active:bg-primary active:text-ink",
            ]}
            href={resolve(`/${href}`)}
            aria-current={isCurrent ? "location" : undefined}
          >
            <span class="font-mono text-xs">{String(i + 1).padStart(2, "0")}</span>
            <span class="sr-only font-semibold md:not-sr-only">{label}</span>
          </a>
        </HardShadow>
      </li>
    {/each}
  </menu>
</nav>
