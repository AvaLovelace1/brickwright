<script lang="ts">
  import ScrollSpy, { type ScrollSpyEvent } from "@fsegurai/scrollspy";
  import "@fontsource-variable/source-sans-3/wght.css";
  import "@fontsource-variable/source-sans-3/wght-italic.css";
  import "@fontsource-variable/rokkitt/wght.css";
  import "@fontsource-variable/rokkitt/wght-italic.css";
  import "@fontsource-variable/source-code-pro/wght.css";
  import "@fontsource-variable/source-code-pro/wght-italic.css";
  import "../app.css";
  import favicon from "#lib/assets/logos/favicon.svg";
  import { Tooltip } from "bits-ui";
  import Header from "#lib/components/Header.svelte";
  import Navbar from "#lib/components/Navbar.svelte";
  import Footer from "#lib/components/Footer.svelte";

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
    return {
      destroy() {
        document.removeEventListener("gumshoeactivate", activate);
        observer.disconnect();
        spy.destroy();
      },
    };
  }
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<Tooltip.Provider>
  <Header />
  <div class="flex-1 pt-17 md:flex md:flex-row">
    <div
      id="section-navigation"
      class="fixed top-17 z-40 w-full border-b border-line md:relative md:top-0 md:w-auto md:border-e md:border-b-0"
    >
      <Navbar
        items={[
          { label: "Overview", href: "#overview" },
          { label: "Results", href: "#results" },
          { label: "Acknowledgments", href: "#acknowledgments" },
          { label: "Citation", href: "#citation" },
        ]}
        {current}
      />
    </div>
    <main
      use:trackSections
      class="mt-15 flex-1 md:mt-0 [&>section]:scroll-mt-32 md:[&>section]:scroll-mt-17"
    >
      {@render children()}
    </main>
  </div>
  <Footer />
</Tooltip.Provider>
