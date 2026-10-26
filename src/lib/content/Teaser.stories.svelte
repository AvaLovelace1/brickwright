<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor, within } from "storybook/test";
  import Teaser from "./Teaser.svelte";
  import { modelFiles } from "#lib/viewer/models.js";
  import { waitForView } from "#lib/story-helpers.js";
  import starryNightImage from "#lib/assets/models/teaser/starry-night-reference.jpg";
  import combineHarvesterImage from "#lib/assets/models/teaser/combine-harvester-reference.png";
  import spaceNeedleImage from "#lib/assets/models/teaser/space-needle-reference.jpg";
  import houseImage from "#lib/assets/models/teaser/house-reference.png";
  import foxImage from "#lib/assets/models/teaser/fox-reference.png";
  import flowerPotImage from "#lib/assets/models/teaser/flower-pot-reference.png";

  const { Story } = defineMeta({
    title: "Content/Teaser",
    component: Teaser,
    tags: ["autodocs"],
    render: template,
    parameters: {
      layout: "fullscreen",
      viewport: {
        options: {
          mobile: { name: "Small phone", styles: { width: "390px", height: "844px" } },
        },
      },
    },
  });
</script>

{#snippet template()}
  <div class="min-h-screen bg-text p-4 text-bg sm:p-8">
    <div class="mx-auto max-w-4xl">
      <Teaser />
    </div>
  </div>
{/snippet}

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Shows the prompt and its model viewer", async () => {
      await expect(canvas.getByRole("region", { name: "Prompt to brick build" })).toBeVisible();
      await expect(
        canvas.getByRole("combobox", {
          name: "Help me build… A lighthouse besieged by a sea serpent",
        }),
      ).toBeVisible();
      await expect(
        canvas.getByRole("figure", { name: "A lighthouse besieged by a sea serpent" }),
      ).toBeVisible();
    });
    await step("Shows the physical validity guarantees", async () => {
      await expect(canvas.getByRole("status")).toHaveTextContent("Physically feasible");
    });
    await step("The selected model starts building once it loads", async () => {
      await waitFor(
        () => expect(canvas.getByRole("button", { name: /^(Pause|Rewind)$/ })).toBeVisible(),
        { timeout: 45_000 },
      );
    });
  }}
/>

<Story
  name="Select a Prompt"
  play={async ({ canvas, userEvent, step }) => {
    const trigger = canvas.getByRole("combobox", { name: /^Help me build…/ });
    await waitForView(canvas.getByRole("figure"));
    const webGLCanvas = document.querySelector("canvas");
    for (const { prompt, model, image } of [
      {
        prompt: "The Starry Night from a painting",
        model: "teaser/starry-night",
        image: starryNightImage,
      },
      {
        prompt: "A combine harvester from an image",
        model: "teaser/combine-harvester",
        image: combineHarvesterImage,
      },
      { prompt: "Seattle’s Space Needle", model: "teaser/space-needle", image: spaceNeedleImage },
      { prompt: "A red house from an image", model: "teaser/house", image: houseImage },
      { prompt: "A fox from an image", model: "teaser/fox", image: foxImage },
      {
        prompt: "Potted lavender from an image",
        model: "teaser/flower-pot",
        image: flowerPotImage,
      },
      { prompt: "Hong Kong’s Victoria Harbour", model: "teaser/victoria-harbour" },
      { prompt: "A mountainside city", model: "teaser/mountainside-city" },
      { prompt: "A cozy ramen bar", model: "teaser/ramen-bar" },
      { prompt: "An Arctic observatory", model: "teaser/arctic-observatory" },
      { prompt: "A poseable crab", model: "teaser/poseable-crab" },
      { prompt: "An articulated fencer", model: "teaser/articulated-fencer" },
      { prompt: "A lighthouse besieged by a sea serpent", model: "teaser/lighthouse-sea-serpent" },
    ]) {
      await step(`Select ${prompt}`, async () => {
        await userEvent.click(trigger);
        await userEvent.click(await screen.findByRole("option", { name: prompt }));
        await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
        await expect(trigger).toHaveAccessibleName(`Help me build… ${prompt}`);
        await expect(trigger).toHaveFocus();
        await expect(canvas.getByRole("figure", { name: prompt })).toBeVisible();
        await expect(canvas.getAllByRole("figure")).toHaveLength(1);
        await expect(canvas.getByRole("link", { name: "Download LDraw" })).toHaveAttribute(
          "href",
          modelFiles(model).ldr,
        );
        const referenceLink = canvas.queryByRole("link", { name: "View reference image" });
        if (image) {
          await expect(referenceLink).toHaveAttribute("href", image);
          const referenceImage = within(referenceLink!).getByRole("img");
          await expect(referenceImage).toHaveAttribute("src", image);
          await expect(referenceImage).toHaveAccessibleName();
          await waitFor(() => expect(referenceImage).toBeVisible());
        } else {
          await expect(referenceLink).toBeNull();
        }
      });
    }
    await step("Every prompt's viewer draws on the same canvas", async () => {
      await waitForView(canvas.getByRole("figure"));
      await expect(document.querySelector("canvas")).toBe(webGLCanvas);
    });
  }}
/>

<Story
  name="Credit a Reference Image"
  play={async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("combobox", { name: /^Help me build…/ }));
    await userEvent.click(await screen.findByRole("option", { name: "Seattle’s Space Needle" }));
    await expect(canvas.getByRole("link", { name: "Jordon Kalilich" })).toHaveAttribute(
      "href",
      "https://commons.wikimedia.org/wiki/File:Space_Needle_2011-07-04.jpg",
    );
    await expect(canvas.getByRole("link", { name: "CC BY-SA 3.0" })).toHaveAttribute(
      "href",
      "https://creativecommons.org/licenses/by-sa/3.0/",
    );
  }}
/>

<Story name="Mobile" globals={{ viewport: { value: "mobile", isRotated: false } }} />
