<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import type { Props as ModelViewerProps } from "./ModelViewer.svelte";
  import ModelViewer from "./ModelViewer.svelte";
  import SharedCanvas from "./SharedCanvas.svelte";
  import { expect, screen, spyOn, waitFor, within } from "storybook/test";
  import { flushSync } from "svelte";
  import { createModel, type ModelView } from "#lib/models.js";
  import { FEASIBILITY_CHECKS } from "#lib/model-diagnostics.js";

  const { Story } = defineMeta({
    title: "Components/Model Viewer",
    render: template,
    component: ModelViewer,
    tags: ["autodocs"],
  });

  const cruiseShip = (caption: string) => createModel("test-examples/cruise-ship", caption);
  let model = $state(cruiseShip("A detailed cruise ship"));
  let autoplayModel = $state(cruiseShip("An autoplaying cruise ship"));
  let retryModel = $state(cruiseShip("A cruise ship that fails to download once"));
  // A fragment gives the model its own cache entry without changing the file that is fetched.
  retryModel.ldrPacked += "#retry";

  function createDiagnosticModel() {
    return createModel(
      "agent-comparison/spaceship-gpt-6-astra-without-brickwright",
      "GPT-6 Astra build without BrickWright",
    );
  }

  let intersectionModel = $state(createDiagnosticModel());
  let highlightedModel = $state(createDiagnosticModel());
  let combinedModel = $state(createDiagnosticModel());
  const diagnosticArgs = { class: "size-80" } satisfies Partial<ModelViewerProps>;

  async function expectDiagnosticsLoaded(model: ModelView) {
    await waitFor(
      () => {
        expect(model.status).toBe("loaded");
        expect(model.diagnostics?.collisions.length).toBeGreaterThan(0);
      },
      { timeout: 45_000 },
    );
  }
</script>

{#snippet template(args: ModelViewerProps)}
  <div class="relative">
    <ModelViewer {...args} bind:model={args.model} />
    <SharedCanvas
      models={[args.model]}
      highlightCollisions={args.highlightCollisions}
      showIntersections={args.showIntersections}
    />
  </div>
{/snippet}

<Story
  name="Default"
  args={{ model, class: "size-64" }}
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
        for (const btn of [prevBtn, playBtn, nextBtn, downloadBtn, viewBtn]) {
          await userEvent.hover(btn);
          const name = btn.textContent!.trim();
          await waitFor(() => expect(screen.getByRole("tooltip", { name })).toBeVisible(), {
            timeout: 5_000,
          });
          // Hovering the container leaves the button while the pointer stays inside the dialog.
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
        await expect(args.model.stepsShown).toBe(1);
      });
      await step("Download button has correct attributes", async () => {
        await expect(downloadBtn).toBeVisible();
        await expect(downloadBtn).toHaveAttribute("href", args.model.ldr);
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
        await userEvent.click(playBtn);
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
      await waitFor(() => expect(args.model.status).toBe("loaded"), { timeout: 45_000 });
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
      await expect(canvas.getByRole("button", { name: "Expand view" })).toHaveFocus();
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
  name="Expanded"
  args={{ model, class: "size-64" }}
  parameters={{ a11y: { context: "body" } }}
  play={async ({ canvas, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Expand view" }));
    // Leave the dialog open for the accessibility audit.
    await screen.findByRole("dialog", { name: "Expanded model view" });
  }}
/>

<Story
  name="Retry After Failed Download"
  args={{ model: retryModel, class: "size-64" }}
  beforeEach={() => {
    const realFetch = globalThis.fetch;
    let failed = false;
    const fetch = spyOn(globalThis, "fetch").mockImplementation((input, init) => {
      if (failed || !String(input).endsWith("#retry")) return realFetch(input, init);
      failed = true;
      return Promise.resolve(new Response(null, { status: 503 }));
    });
    return () => fetch.mockRestore();
  }}
  play={async ({ canvas, userEvent }) => {
    await expect(await canvas.findByRole("alert", {}, { timeout: 45_000 })).toHaveTextContent(
      "Unable to load",
    );
    await expect(canvas.getByRole("figure")).toHaveAttribute("aria-busy", "false");
    await userEvent.click(canvas.getByRole("button", { name: "Retry model" }));
    await expect(
      await canvas.findByRole("slider", { name: "Steps shown" }, { timeout: 45_000 }),
    ).toBeVisible();
  }}
/>

<Story
  name="Status Badge"
  args={{
    model,
    class: "h-80 w-full max-w-xl",
    badge: {
      text: "Physically feasible",
      description: FEASIBILITY_CHECKS,
    },
  }}
  play={async ({ canvas, args, step }) => {
    const badge = args.badge!;
    await step("Badge and description appear on the figure", async () => {
      await expect(canvas.getByRole("status")).toHaveTextContent(badge.text);
      for (const item of badge.description!) await expect(canvas.getByText(item)).toBeVisible();
      await expect(canvas.getByRole("figure", { name: /A detailed cruise ship/ })).toBeVisible();
    });
  }}
/>

<Story
  name="Collisions Badge"
  args={{
    model,
    class: "size-64",
    badge: { text: "Collisions", tone: "danger" },
  }}
  play={async ({ canvas, step }) => {
    await step("A warning badge works without a description", async () => {
      const badge = canvas.getByRole("status");
      await expect(badge).toBeVisible();
      await expect(badge).toHaveTextContent("Collisions");
      await expect(canvas.getByRole("figure", { name: "A detailed cruise ship" })).toBeVisible();
    });
  }}
/>

<Story
  name="Intersections"
  args={{ ...diagnosticArgs, model: intersectionModel, showIntersections: true }}
  play={async ({ canvas, args, userEvent, step }) => {
    await expectDiagnosticsLoaded(args.model);
    await step("Intersections are labelled on the complete build", async () => {
      await expect(canvas.getByText("Intersections", { exact: true })).toBeVisible();
    });
    await step("The legend follows the completed-build overlay", async () => {
      await userEvent.click(canvas.getByRole("button", { name: "Rewind" }));
      await expect(canvas.queryByText("Intersections", { exact: true })).toBeNull();
      canvas.getByRole("slider", { name: "Steps shown" }).focus();
      await userEvent.keyboard("{End}");
      await expect(canvas.getByText("Intersections", { exact: true })).toBeVisible();
      // The Rewind tooltip is still fading in, and the a11y check measures its contrast
      await Promise.all(document.getAnimations().map((animation) => animation.finished));
    });
  }}
/>

<Story
  name="Colliding Bricks"
  args={{ ...diagnosticArgs, model: highlightedModel, highlightCollisions: true }}
  play={async ({ canvas, args }) => {
    await expectDiagnosticsLoaded(args.model);
    await expect(canvas.queryByText("Intersections", { exact: true })).toBeNull();
  }}
/>

<Story
  name="Combined Diagnostics"
  args={{
    ...diagnosticArgs,
    model: combinedModel,
    highlightCollisions: true,
    showIntersections: true,
  }}
  play={async ({ canvas, args }) => {
    await expectDiagnosticsLoaded(args.model);
    await expect(canvas.getByRole("status")).toHaveTextContent(/^Invalid$/);
    await expect(canvas.getByText("Intersections", { exact: true })).toBeVisible();
  }}
/>
