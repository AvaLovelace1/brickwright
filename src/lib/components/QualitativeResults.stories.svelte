<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor, within } from "storybook/test";
  import { Tooltip } from "bits-ui";
  import type Swiper from "swiper";
  import QualitativeResults from "./QualitativeResults.svelte";
  import { agents, prompts, resultModelName } from "#lib/experiment-results.js";

  const { Story } = defineMeta({
    title: "Components/QualitativeResults",
    component: QualitativeResults,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });
</script>

{#snippet template()}
  <Tooltip.Provider>
    <div class="mx-auto max-w-4xl p-4 sm:p-8"><QualitativeResults /></div>
  </Tooltip.Provider>
{/snippet}

<Story
  name="Agent Selection and Diagnostics"
  play={async ({ canvas, canvasElement, userEvent, step }) => {
    const progress = canvas.getByRole("status", { name: "Prompt position" });
    const agentSelect = canvas.getByRole("button", { name: /^Agent model/ });
    const currentAgent = agents.find((agent) => agent.label === agentSelect.textContent?.trim())!;
    const selectedAgent =
      agents.find((agent) => agent.value !== currentAgent.value) ?? currentAgent;
    const promptIndex = Math.min(1, prompts.length - 1);
    const prompt = prompts[promptIndex];
    const position = `${promptIndex + 1} / ${prompts.length}`;
    const collisions = canvas.getByRole("checkbox", { name: "Highlight colliding bricks" });
    await userEvent.click(collisions);
    await expect(collisions).toBeChecked();
    await expect(progress).toHaveTextContent(`1 / ${prompts.length}`);
    // Arrange a non-default prompt; native arrow and swipe input is covered by the browser test.
    const carousel = canvasElement.querySelector(".swiper") as HTMLElement & { swiper: Swiper };
    await waitFor(() => expect(carousel.swiper?.initialized).toBe(true));
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
          const filename = `${resultModelName(prompt, selectedAgent, method)}.ldr`;
          const result = within(
            canvas.getByRole("group", { name: `${methodLabel} (${selectedAgent.label})` }),
          );
          await expect(
            result.getByRole("heading", { name: `${methodLabel} (${selectedAgent.label})` }),
          ).toBeVisible();
          const viewer = result.getByRole("figure", {
            name: `${prompt.title} — ${selectedAgent.label} — ${methodLabel}`,
          });
          viewer.scrollIntoView({ block: "center" });
          const download = within(viewer).getByRole("link", { name: "Download LDraw" });
          await expect(download).toHaveAttribute(
            "href",
            expect.stringContaining(`/models/results/${filename}`),
          );
          await expect(download).toHaveAttribute("download", filename);
          await waitFor(() => expect(viewer).toHaveAttribute("aria-busy", "false"), {
            timeout: 45_000,
          });
        }
      },
    );
  }}
/>
