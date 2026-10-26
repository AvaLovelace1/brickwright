<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor, within } from "storybook/test";
  import type Swiper from "swiper";
  import QualitativeResults from "./QualitativeResults.svelte";
  import { agents, prompts, resultModelName } from "#lib/content/experiment-results.js";
  import { modelFiles } from "#lib/viewer/models.js";
  import { waitForModel } from "#lib/story-helpers.js";

  const { Story } = defineMeta({
    title: "Content/QualitativeResults",
    component: QualitativeResults,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });

  /** The carousel element, once Swiper has initialized it. */
  async function initializedCarousel(canvasElement: HTMLElement) {
    const carousel = canvasElement.querySelector(".swiper") as HTMLElement & { swiper: Swiper };
    await waitFor(() => expect(carousel.swiper?.initialized).toBe(true));
    return carousel;
  }

  /** The drawn 3D views on the carousel's current slide. */
  function activeViews(canvasElement: HTMLElement) {
    const slide = canvasElement.querySelector<HTMLElement>(".swiper-slide-active")!;
    return within(slide).queryAllByRole("group", { name: /interactive 3D view/ });
  }
</script>

{#snippet template()}
  <div class="mx-auto max-w-4xl p-4 sm:p-8"><QualitativeResults /></div>
{/snippet}

<Story
  name="Agent Selection and Diagnostics"
  play={async ({ canvas, canvasElement, userEvent, step }) => {
    const progress = canvas.getByRole("status", { name: "Prompt position" });
    const agentSelect = canvas.getByRole("combobox", { name: /^Agent model/ });
    const currentAgent = agents.find((agent) => agent.label === agentSelect.textContent?.trim())!;
    const selectedAgent = agents.find((agent) => agent.value !== currentAgent.value)!;
    const promptIndex = 1;
    const prompt = prompts[promptIndex];
    const position = `${promptIndex + 1} / ${prompts.length}`;
    const collisions = canvas.getByRole("checkbox", { name: "Highlight colliding bricks" });
    await userEvent.click(collisions);
    await expect(collisions).toBeChecked();
    await expect(progress).toHaveTextContent(`1 / ${prompts.length}`);
    // Jump to a non-default prompt without animating.
    const carousel = await initializedCarousel(canvasElement);
    carousel.swiper.slideToLoop(promptIndex, 0);
    await waitFor(() => expect(progress).toHaveTextContent(position));

    await step("Changing the agent preserves the prompt and diagnostic settings", async () => {
      await userEvent.click(agentSelect);
      const option = await screen.findByRole("option", { name: selectedAgent.label });
      await waitFor(() => expect(option).toBeVisible());
      await userEvent.click(option);
      await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
      await expect(progress).toHaveTextContent(position);
      await expect(collisions).toBeChecked();
    });
    await step(
      "Each titled result loads its matching build and exposes a descriptive download",
      async () => {
        await waitFor(() =>
          expect(canvas.getAllByRole("figure", { hidden: true })).toHaveLength(2),
        );
        for (const method of ["baseline", "brickwright"] as const) {
          const methodLabel = method === "baseline" ? selectedAgent.baseline : "BrickWright";
          const name = resultModelName(prompt, selectedAgent, method);
          const result = within(
            canvas.getByRole("group", { name: `${methodLabel} (${selectedAgent.label})` }),
          );
          await expect(
            result.getByRole("heading", { name: `${methodLabel} (${selectedAgent.label})` }),
          ).toBeVisible();
          const viewer = result.getByRole("figure", {
            name: `${prompt.title} — ${selectedAgent.label} — ${methodLabel}`,
          });
          const download = within(viewer).getByRole("link", { name: "Download LDraw" });
          await expect(download).toHaveAttribute("href", modelFiles(`results/${name}`).ldr);
          await expect(download).toHaveAttribute("download", `${name}.ldr`);
          await waitForModel(viewer);
        }
      },
    );
  }}
/>

<Story
  name="Slide Animation"
  play={async ({ canvas, canvasElement }) => {
    const carousel = await initializedCarousel(canvasElement);
    const wrapper = carousel.querySelector<HTMLElement>(".swiper-wrapper")!;
    const positions = [wrapper.getBoundingClientRect().left];
    canvas.getByRole("button", { name: "Next prompt" }).click();
    for (let frame = 0; frame < 30; frame++) {
      await new Promise(requestAnimationFrame);
      positions.push(wrapper.getBoundingClientRect().left);
    }
    // The first slide animates through the positions between its start and end.
    const [start, end] = [positions[0], positions.at(-1)];
    await expect(positions.some((position) => position !== start && position !== end)).toBe(true);
  }}
/>

<Story
  name="Next Prompt"
  play={async ({ canvas, canvasElement, userEvent }) => {
    await waitFor(() => expect(activeViews(canvasElement)).toHaveLength(2), { timeout: 15_000 });
    await userEvent.click(canvas.getByRole("button", { name: "Next prompt" }));
    // Both incoming builds load, even while the outgoing ones keep the page busy.
    await waitFor(() => expect(activeViews(canvasElement)).toHaveLength(2), { timeout: 15_000 });
  }}
/>

<Story
  name="Navigating Right After a Resize"
  play={async ({ canvas, canvasElement }) => {
    const progress = canvas.getByRole("status", { name: "Prompt position" });
    const next = canvas.getByRole("button", { name: "Next prompt" });
    const carousel = await initializedCarousel(canvasElement);
    // Instant slides, as with reduced motion, let each click land within frames of the resize.
    carousel.swiper.params.speed = 0;
    const frames = async (count: number) => {
      for (let frame = 0; frame < count; frame++) await new Promise(requestAnimationFrame);
    };
    for (let delay = 0; delay < 5; delay++) {
      carousel.style.minHeight = delay % 2 ? "" : `${carousel.offsetHeight + 100}px`;
      await frames(delay);
      next.click();
      await frames(5);
      await expect(progress).toHaveTextContent(`${delay + 2} / ${prompts.length}`);
    }
  }}
/>

<Story
  name="Browsing Keeps the 3D Canvas"
  play={async ({ canvas, canvasElement }) => {
    const progress = canvas.getByRole("status", { name: "Prompt position" });
    const carousel = await initializedCarousel(canvasElement);
    await waitFor(() => expect(activeViews(canvasElement)).toHaveLength(2), { timeout: 15_000 });
    const webGLCanvas = document.querySelector("canvas");
    for (let promptIndex = 1; promptIndex <= 3; promptIndex++) {
      carousel.swiper.slideToLoop(promptIndex, 0);
      await waitFor(() =>
        expect(progress).toHaveTextContent(`${promptIndex + 1} / ${prompts.length}`),
      );
      await waitFor(() => expect(activeViews(canvasElement)).toHaveLength(2), {
        timeout: 15_000,
      });
    }
    // Every slide's viewers draw on one canvas, keeping its WebGL context.
    await expect(document.querySelector("canvas")).toBe(webGLCanvas);
  }}
/>
