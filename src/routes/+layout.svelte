<script lang="ts">
  import { page } from "$app/state";
  import "@fontsource-variable/source-sans-3/wght.css";
  import "@fontsource-variable/source-sans-3/wght-italic.css";
  import "@fontsource-variable/rokkitt/wght.css";
  import "@fontsource-variable/rokkitt/wght-italic.css";
  import "@fontsource-variable/source-code-pro/wght.css";
  import "@fontsource-variable/source-code-pro/wght-italic.css";
  import "../app.css";
  import favicon from "$lib/assets/logos/favicon.svg";
  import { Tooltip } from "bits-ui";
  import Header from "$lib/components/Header.svelte";
  import Navbar from "$lib/components/Navbar.svelte";
  import Footer from "$lib/components/Footer.svelte";

  let { children } = $props();
</script>

<svelte:head><link rel="icon" href={favicon} /></svelte:head>

<Tooltip.Provider>
  <Header />
  <div class="flex-1 pt-17 md:flex md:flex-row">
    <div
      class="fixed top-17 z-40 w-full border-b border-line md:relative md:top-0 md:w-auto md:border-e md:border-b-0"
    >
      <Navbar
        items={[
          { label: "Overview", href: "/" },
          { label: "Results", href: "/results" },
          { label: "Acknowledgments", href: "/acknowledgments" },
          { label: "Citation", href: "/citation" },
        ]}
        current={page.url.pathname}
      />
    </div>
    <main class="mt-15 flex-1 md:mt-0">{@render children()}</main>
  </div>
  <Footer />
</Tooltip.Provider>
