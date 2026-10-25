<script lang="ts">
  import ScrollSpy, { type ScrollSpyEvent } from "@fsegurai/scrollspy";
  import "../app.css";
  import favicon from "#lib/assets/logos/favicon.svg";
  import { Tooltip } from "bits-ui";
  import Header from "#lib/components/Header.svelte";
  import Navbar from "#lib/components/Navbar.svelte";
  import Footer from "#lib/components/Footer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";

  let { children } = $props();
  let current = $state("#overview");

  function trackSections(main: HTMLElement) {
    const firstSection = main.querySelector<HTMLElement>("section[id]");
    if (!firstSection) return;

    function activate(event: CustomEvent<ScrollSpyEvent>) {
      if (main.contains(event.detail.target)) current = `#${event.detail.target.id}`;
    }
    document.addEventListener("gumshoeactivate", activate);
    const spy = new ScrollSpy("#section-navigation", {
      offset: () => parseFloat(getComputedStyle(firstSection).scrollMarginTop) + 1,
      bottomThreshold: 1,
      reflow: true,
    });
    // Recheck after content changes size, even when the visitor hasn't scrolled
    const observer = new ResizeObserver(() => spy.detect());
    for (const section of main.querySelectorAll("section[id]")) observer.observe(section);
    return () => {
      document.removeEventListener("gumshoeactivate", activate);
      observer.disconnect();
      spy.destroy();
    };
  }
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<Tooltip.Provider>
  <a
    href="#main-content"
    class="sr-only focus:not-sr-only focus:fixed focus:top-2 focus:left-2 focus:z-[100] focus:bb-border focus:bg-surface focus:px-4 focus:py-2 focus:text-text active:bg-primary active:text-ink"
    >Skip to content</a
  >
  <Header />
  <div class="flex-1 pt-17 md:flex md:flex-row">
    <div
      id="section-navigation"
      class="fixed top-17 z-40 w-full border-b border-line md:relative md:top-0 md:w-auto md:border-e md:border-b-0"
    >
      <Navbar
        items={[
          { label: "Overview", href: "#overview" },
          { label: "Motivation", href: "#motivation" },
          { label: "Method", href: "#method" },
          { label: "Experiments", href: "#experiments" },
          { label: "Acknowledgments", href: "#acknowledgments" },
          { label: "Citation", href: "#citation" },
        ]}
        {current}
      />
    </div>
    <main
      id="main-content"
      tabindex="-1"
      {@attach trackSections}
      class="relative mt-15 min-w-0 flex-1 scroll-mt-32 md:mt-0 md:scroll-mt-17 [&>section]:scroll-mt-32 md:[&>section]:scroll-mt-17"
    >
      {@render children()}
      <SharedCanvas />
    </main>
  </div>
  <Footer />
</Tooltip.Provider>
