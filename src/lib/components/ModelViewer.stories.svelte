<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import type { Props as ModelViewerProps } from "./ModelViewer.svelte";
  import ModelViewer from "./ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";
  import type { LegoModelView } from "#lib/components/ModelViewer.svelte";
  import ldr from "#lib/assets/ldr/cruise-ship.ldr?url";
  import ldrPacked from "#lib/assets/ldr/cruise-ship.ldr_Packed.mpd?url";
  import { expect, screen, waitFor, within } from "storybook/test";
  import { Tooltip as BitsTooltip } from "bits-ui";
  import { flushSync } from "svelte";

  const { Story } = defineMeta({
    title: "Components/Model Viewer",
    render: template,
    component: ModelViewer,
    tags: ["autodocs"],
  });

  let model = $state<LegoModelView>({
    ldr,
    ldrPacked,
    caption: "A detailed cruise ship",
    stepsShown: 1,
    maxSteps: 600,
  });

  let autoplayModel = $state<LegoModelView>({
    ldr,
    ldrPacked,
    caption: "An autoplaying cruise ship",
    stepsShown: 1,
    maxSteps: 600,
  });
</script>

{#snippet template(args: ModelViewerProps)}
  <BitsTooltip.Provider>
    <div class="relative">
      <ModelViewer {...args} bind:model={args.model} />
      <SharedCanvas models={[args.model]} />
    </div>
  </BitsTooltip.Provider>
{/snippet}

<Story
  name="Default"
  args={{ model: model, class: "size-64" }}
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
        await waitFor(() => expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull(), {
          timeout: 5_000,
        });
        await userEvent.keyboard("{Escape}");
      }
      await waitFor(
        () => {
          expect(screen.queryByRole("dialog")).toBeNull();
          expect(screen.queryByRole("presentation")).toBeNull();
        },
        { timeout: 5_000 },
      );
    }

    async function expectPaused() {
      const stepsShownAfterPause = args.model.stepsShown;
      await sleep(200);
      await expect(args.model.stepsShown).toBe(stepsShownAfterPause);
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
          await waitFor(() => expect(screen.getByRole("tooltip", { name })).toBeVisible(), {
            timeout: 5_000,
          });
          // Calling unhover() would target document.body and set pointer-events: none when the dialog is open
          await userEvent.hover(container);
          await waitFor(() => expect(screen.queryByRole("tooltip", { hidden: true })).toBeNull(), {
            timeout: 5_000,
          });
        }
      });
      await step("Next button steps forward", async () => {
        args.model.stepsShown = 1;
        await expect(nextBtn).toBeVisible();
        await userEvent.click(nextBtn);
        await expect(args.model.stepsShown).toBe(2);
      });
      await step("Previous button steps backward", async () => {
        args.model.stepsShown = 1;
        await expect(prevBtn).toBeVisible();
        await userEvent.click(prevBtn);
        await expect(args.model.stepsShown).toBe(1);
        await userEvent.click(prevBtn);
        await expect(args.model.stepsShown).toBe(1); // does not underflow
      });
      await step("Download button has correct attributes", async () => {
        await expect(downloadBtn).toBeVisible();
        await expect(downloadBtn).toHaveAttribute("href", ldr);
        await expect(downloadBtn).toHaveAttribute("download", "cruise-ship.ldr");
      });
      await step("Play button plays", async () => {
        args.model.stepsShown = 1;
        const initialStepsShown = args.model.stepsShown;
        await expect(playBtn).toBeVisible();
        await userEvent.click(playBtn);
        await waitFor(() => expect(args.model.stepsShown).toBeGreaterThan(initialStepsShown));
      });
      await step("Pause button pauses", async () => {
        const pauseBtn = canvas.getByRole("button", { name: /pause/i });
        await expect(pauseBtn).toBeVisible();
        await userEvent.click(pauseBtn);
        await expectPaused();
      });
      await step("Rewind button rewinds to start and is paused afterward", async () => {
        args.model.stepsShown = args.model.maxSteps - 2;
        await userEvent.click(playBtn); // Play the one remaining step
        await waitFor(() => expect(args.model.stepsShown).toBe(args.model.maxSteps));

        const rewindBtn = canvas.getByRole("button", { name: /rewind/i });
        await expect(rewindBtn).toBeVisible();
        await userEvent.click(rewindBtn);
        await expect(args.model.stepsShown).toBe(1);
        await expectPaused();
      });
      await step("Rewind pauses even before the next playback tick", async () => {
        flushSync(() => {
          args.model.stepsShown = args.model.maxSteps - 1;
        });
        flushSync(() => playBtn.click());
        flushSync(() => nextBtn.click());
        flushSync(() => canvas.getByRole("button", { name: /rewind/i }).click());
        await expect(canvas.getByRole("button", { name: /^play$/i })).toBeVisible();
        await expect(args.model.stepsShown).toBe(1);
        await expectPaused();
      });
    }

    await step("Caption labels the figure", async () => {
      await expect(canvas.getByRole("figure", { name: /A detailed cruise ship/ })).toBeVisible();
    });
    await step("The viewer starts with a complete build and can be rewound", async () => {
      await waitFor(() => expect(args.model.loaded).toBe(true), { timeout: 45_000 });
      await waitFor(() => expect(args.model.stepsShown).toBe(args.model.maxSteps));
      await userEvent.click(canvas.getByRole("button", { name: "Rewind" }));
      await expect(args.model.stepsShown).toBe(1);
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

<Story
  name="Autoplay"
  args={{ model: autoplayModel, class: "size-64", autoplay: true }}
  play={async ({ canvas, step }) => {
    await step("Playback starts on its own once the model has loaded", async () => {
      await waitFor(() => expect(autoplayModel.stepsShown).toBeGreaterThan(1), {
        timeout: 45_000,
      });
      await expect(canvas.getByRole("button", { name: /pause/i })).toBeVisible();
    });
  }}
/>

<Story
  name="Hidden Caption"
  args={{ model: model, class: "size-64", showCaption: false }}
  play={async ({ canvas, args, step }) => {
    await step("Figure retains its accessible name without a visible caption", async () => {
      const figure = canvas.getByRole("figure", { name: args.model.caption });
      await expect(figure).toBeVisible();
      await expect(figure.querySelector("figcaption")).toBeNull();
    });
  }}
/>

<Story
  name="Status Badge"
  args={{
    model: model,
    class: "h-80 w-full max-w-xl",
    badge: {
      text: "Physically feasible",
      description: "Real LEGO® parts · No intersecting or floating parts · One connected component",
    },
  }}
  play={async ({ canvas, args, step }) => {
    const badge = args.badge!;
    await step("Badge and description appear alongside the caption", async () => {
      await expect(canvas.getByRole("status")).toHaveTextContent(badge.text);
      await expect(canvas.getByText(badge.description!)).toBeVisible();
      await expect(canvas.getByRole("figure", { name: /A detailed cruise ship/ })).toBeVisible();
    });
  }}
/>

<Story
  name="Collisions Badge"
  args={{
    model: model,
    class: "size-64",
    showCaption: false,
    badge: { text: "Collisions", tone: "danger" },
  }}
  play={async ({ canvas, step }) => {
    await step("A warning badge works without a description or visible caption", async () => {
      const badge = canvas.getByRole("status");
      await expect(badge).toBeVisible();
      await expect(badge).toHaveTextContent("Collisions");
      await expect(canvas.getByRole("figure", { name: "A detailed cruise ship" })).toBeVisible();
    });
  }}
/>
