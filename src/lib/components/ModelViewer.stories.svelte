<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import type { Props as ModelViewerProps } from "./ModelViewer.svelte";
  import ModelViewer from "./ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";
  import type { LegoModelView } from "#lib/components/ModelViewer.svelte";
  import ldr from "#lib/assets/ldr/cruise-ship.ldr?url";
  import ldrPacked from "#lib/assets/ldr/cruise-ship.ldr_Packed.mpd?url";
  import { expect, screen, waitFor, waitForElementToBeRemoved, within } from "storybook/test";
  import { Tooltip as BitsTooltip } from "bits-ui";

  const { Story } = defineMeta({
    title: "Components/Model Viewer",
    render: template,
    component: ModelViewer,
    tags: ["autodocs"],
  });

  let models = $state<LegoModelView[]>([
    { ldr, ldrPacked, caption: "A detailed cruise ship", bricksShown: 1, maxBricks: 600 },
  ]);

  let autoplayModels = $state<LegoModelView[]>([
    { ldr, ldrPacked, caption: "An autoplaying cruise ship", bricksShown: 1, maxBricks: 600 },
  ]);
</script>

{#snippet template(args: ModelViewerProps)}
  <BitsTooltip.Provider>
    <div class="relative">
      <ModelViewer {...args} bind:model={args.model} />
      <SharedCanvas bind:models />
    </div>
  </BitsTooltip.Provider>
{/snippet}

<Story
  name="Default"
  args={{ model: models[0], class: "size-64" }}
  play={async ({ canvas, canvasElement, step, userEvent, args }) => {
    async function sleep(ms: number) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function openDialog() {
      await userEvent.click(canvas.getByRole("button", { name: /expand view/i }));
      await waitFor(() => expect(screen.getByRole("dialog")).toBeVisible());
    }

    async function closeDialog(method: "button" | "clickOutside" | "keyboard" = "keyboard") {
      const dialog = screen.getByRole("dialog");
      if (method === "button") {
        await userEvent.click(within(dialog).getByRole("button", { name: /close/i }));
      } else if (method === "clickOutside") {
        await userEvent.click(screen.getByRole("presentation"));
      } else if (method === "keyboard") {
        // Let tooltips close before pressing Escape
        await userEvent.hover(dialog);
        await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
        await userEvent.keyboard("{Escape}");
      }
      await waitForElementToBeRemoved(() => screen.queryByRole("dialog"));
    }

    async function expectPaused() {
      const bricksShownAfterPause = args.model.bricksShown;
      await sleep(200);
      await expect(args.model.bricksShown).toBe(bricksShownAfterPause);
    }

    async function checkButtons(container: HTMLElement) {
      const canvas = within(container);
      const nextBtn = canvas.getByRole("button", { name: /next step/i });
      const playBtn = canvas.getByRole("button", { name: /play/i });
      const prevBtn = canvas.getByRole("button", { name: /previous step/i });
      const downloadBtn = canvas.getByRole("link", { name: /download/i });
      const viewBtn = canvas.getByRole("button", { name: /view/i });

      await step("All buttons show tooltip on hover", async () => {
        for (const { btn, name } of [
          { btn: prevBtn, name: /previous step/i },
          { btn: playBtn, name: /play/i },
          { btn: nextBtn, name: /next step/i },
          { btn: downloadBtn, name: /download/i },
          { btn: viewBtn, name: /view/i },
        ]) {
          await userEvent.hover(btn);
          const tooltipContent = await screen.findByRole("tooltip", { name });
          await waitFor(() => expect(tooltipContent).toBeVisible());
          // Calling unhover() would target document.body and set pointer-events: none when the dialog is open
          await userEvent.hover(container);
          await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
        }
      });
      await step("Next button steps forward", async () => {
        args.model.bricksShown = 1;
        await expect(nextBtn).toBeVisible();
        await userEvent.click(nextBtn);
        await expect(args.model.bricksShown).toBe(2);
      });
      await step("Previous button steps backward", async () => {
        args.model.bricksShown = 1;
        await expect(prevBtn).toBeVisible();
        await userEvent.click(prevBtn);
        await expect(args.model.bricksShown).toBe(1);
        await userEvent.click(prevBtn);
        await expect(args.model.bricksShown).toBe(1); // does not underflow
      });
      await step("Download button has correct attributes", async () => {
        await expect(downloadBtn).toBeVisible();
        await expect(downloadBtn).toHaveAttribute("href", ldr);
        await expect(downloadBtn).toHaveAttribute("download", "cruise-ship.ldr");
      });
      await step("Play button plays", async () => {
        args.model.bricksShown = 1;
        const initialBricksShown = args.model.bricksShown;
        await expect(playBtn).toBeVisible();
        await userEvent.click(playBtn);
        await waitFor(() => expect(args.model.bricksShown).toBeGreaterThan(initialBricksShown));
      });
      await step("Pause button pauses", async () => {
        const pauseBtn = canvas.getByRole("button", { name: /pause/i });
        await expect(pauseBtn).toBeVisible();
        await userEvent.click(pauseBtn);
        await expectPaused();
      });
      await step("Rewind button rewinds to start and is paused afterward", async () => {
        args.model.bricksShown = args.model.maxBricks - 2;
        await userEvent.click(playBtn); // Play the one remaining step
        await waitFor(() => expect(args.model.bricksShown).toBe(args.model.maxBricks));

        const rewindBtn = canvas.getByRole("button", { name: /rewind/i });
        await expect(rewindBtn).toBeVisible();
        await userEvent.click(rewindBtn);
        await expect(args.model.bricksShown).toBe(1);
        await expectPaused();
      });
    }

    await step("Caption labels the figure", async () => {
      await expect(canvas.getByRole("figure", { name: /A detailed cruise ship/ })).toBeVisible();
    });
    await step("Buttons are functional", async () => {
      await checkButtons(canvasElement);
    });
    await step("All open/close methods work", async () => {
      for (const method of ["button", "clickOutside", "keyboard"] as const) {
        await openDialog();
        await closeDialog(method);
      }
    });

    await openDialog();
    await step("Clicking inside the popup doesn't close the dialog", async () => {
      const dialog = screen.getByRole("dialog");
      await userEvent.click(dialog);
      await expect(dialog).toBeVisible();
    });
    await step("Buttons are functional in popup", async () => {
      await checkButtons(screen.getByRole("dialog"));
    });
    await closeDialog();
  }}
/>

{#snippet autoplayTemplate(args: ModelViewerProps)}
  <BitsTooltip.Provider>
    <div class="relative">
      <ModelViewer {...args} bind:model={args.model} />
      <SharedCanvas bind:models={autoplayModels} />
    </div>
  </BitsTooltip.Provider>
{/snippet}

<Story
  name="Autoplay"
  template={autoplayTemplate}
  args={{ model: autoplayModels[0], class: "size-64", autoplay: true }}
  play={async ({ canvas, step }) => {
    await step("Playback starts on its own once the model has loaded", async () => {
      await waitFor(() => expect(autoplayModels[0].bricksShown).toBeGreaterThan(1), {
        timeout: 45_000,
      });
      await expect(canvas.getByRole("button", { name: /pause/i })).toBeVisible();
    });
  }}
/>
