<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Layout from "./+layout.svelte";
  import { createRawSnippet } from "svelte";
  import { expect, within } from "storybook/test";

  const { Story } = defineMeta({
    title: "Layouts/Main Layout",
    component: Layout,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
    args: {
      children: createRawSnippet(() => ({
        render: () => "<div class='p-8 h-[1024px]'><p>This is the layout body</p></div>",
      })),
    },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    const header = canvas.getByRole("banner");
    const nav = canvas.getByRole("navigation");
    const main = canvas.getByRole("main");
    const footer = canvas.getByRole("contentinfo");
    await step("Layout has the expected structure", async () => {
      await expect(header).toBeVisible();
      await expect(nav).toBeVisible();
      await expect(main).toBeVisible();
      await expect(main).toHaveTextContent("This is the layout body");
      await expect(footer).toBeVisible();
    });
    await step("Bottom of header is flush with top of main", async () => {
      const headerBottom = header.getBoundingClientRect().bottom;
      const mainTop = main.getBoundingClientRect().top;
      await expect(headerBottom).toBe(mainTop);
    });
    await step("Header stays sticky when scrolled", async () => {
      window.scrollTo({ top: 0, behavior: "instant" });
      const headerTopBeforeScroll = header.getBoundingClientRect().top;
      await expect(headerTopBeforeScroll).toBe(0);
      window.scrollTo({ top: 800, behavior: "instant" });
      const headerTopAfterScroll = header.getBoundingClientRect().top;
      await expect(headerTopAfterScroll).toBe(0);
    });
    await step("Nav links stay sticky when scrolled", async () => {
      window.scrollTo({ top: 0, behavior: "instant" });
      const firstLink = within(nav).queryAllByRole("link")[0];
      const linkTopBeforeScroll = firstLink.getBoundingClientRect().top;
      window.scrollTo({ top: 800, behavior: "instant" });
      const linkTopAfterScroll = firstLink.getBoundingClientRect().top;
      await expect(linkTopAfterScroll).toBe(linkTopBeforeScroll);
    });
  }}
/>

<Story
  name="Mobile"
  parameters={{ viewport: { defaultViewport: "mobile2" } }}
  play={async ({ canvas, step }) => {
    const nav = canvas.getByRole("navigation");
    const main = canvas.getByRole("main");
    await step("Bottom of nav is flush with top of main", async () => {
      const navBottom = nav.getBoundingClientRect().bottom;
      const mainTop = main.getBoundingClientRect().top;
      await expect(navBottom).toBe(mainTop);
    });
    await step("Whole nav stays sticky when scrolled", async () => {
      window.scrollTo({ top: 0, behavior: "instant" });
      const navTopBeforeScroll = nav.getBoundingClientRect().top;
      window.scrollTo({ top: 800, behavior: "instant" });
      const navTopAfterScroll = nav.getBoundingClientRect().top;
      await expect(navTopAfterScroll).toBe(navTopBeforeScroll);
    });
  }}
/>
