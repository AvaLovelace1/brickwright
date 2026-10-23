<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor } from "storybook/test";
  import { Tooltip } from "bits-ui";
  import Teaser from "./Teaser.svelte";
  import { createModel } from "#lib/models.js";
  import referenceImageUrl from "#lib/assets/models/teaser/combine-harvester-reference.png";

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
  <Tooltip.Provider>
    <div class="min-h-screen bg-text p-4 text-bg sm:p-8">
      <div class="mx-auto max-w-4xl">
        <Teaser />
      </div>
    </div>
  </Tooltip.Provider>
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
        {
          timeout: 45_000,
        },
      );
    });
  }}
/>

<Story
  name="Select a Prompt"
  play={async ({ canvas, userEvent, step }) => {
    const trigger = canvas.getByRole("combobox", { name: /^Help me build…/ });
    for (const [prompt, filename] of [
      ["A combine harvester from an image", "combine-harvester"],
      ["Hong Kong’s Victoria Harbour", "victoria-harbour"],
      ["A poseable crab", "poseable-crab"],
      ["A lighthouse besieged by a sea serpent", "lighthouse-sea-serpent"],
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
          createModel(`teaser/${filename}`, prompt).ldr,
        );
        const referenceImage = canvas.queryByRole("img", {
          name: /combine harvester/,
        });
        if (filename === "combine-harvester") {
          await expect(referenceImage).toBeVisible();
          await expect(canvas.getByRole("link", { name: "View reference image" })).toHaveAttribute(
            "href",
            referenceImageUrl,
          );
        } else {
          await expect(referenceImage).toBeNull();
        }
      });
    }
  }}
/>

<Story name="Mobile" globals={{ viewport: { value: "mobile", isRotated: false } }} />
