<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import { tick } from "svelte";
  import VideoThumbnail from "./VideoThumbnail.svelte";
  import { loaded } from "./VideoThumbnailScene.svelte";
  import { FEASIBILITY_CHECKS } from "#lib/viewer/model-diagnostics.js";
  import { SUBTITLE } from "#lib/paper.js";
  import { DURATION, FPS, SCENES, frameAt, type Frame } from "#lib/video-thumbnail/timeline.js";

  declare global {
    interface Window {
      /** Frame-accurate playback controls. */
      videoThumbnail?: {
        duration: number;
        fps: number;
        ready: Promise<unknown>;
        seek: (time: number) => Promise<void>;
      };
    }
  }

  const { Story } = defineMeta({
    title: "Content/Video Thumbnail",
    component: VideoThumbnail,
    render: template,
    parameters: { layout: "fullscreen" },
  });

  let time = $state(DURATION);

  function exposeControls() {
    window.videoThumbnail = {
      duration: DURATION,
      fps: FPS,
      ready: Promise.all([loaded, document.fonts.ready]),
      seek(seconds) {
        time = seconds;
        return tick();
      },
    };
    return () => delete window.videoThumbnail;
  }

  const firstFrame = (matches: (frame: Frame) => boolean) =>
    Array.from({ length: Math.ceil(DURATION * FPS) }, (_, i) => i / FPS).find((t) =>
      matches(frameAt(t)),
    )!;
</script>

{#snippet template()}
  <div class="w-fit" {@attach exposeControls}>
    <VideoThumbnail {time} />
  </div>
{/snippet}

<Story
  name="Default"
  play={async ({ canvas, step }) => {
    await step("Ends on the full title, as the video starts", async () => {
      await expect(canvas.getByRole("heading", { name: /BrickWright/ })).toBeVisible();
      await expect(canvas.getByText(SUBTITLE)).toBeVisible();
    });
    await document.fonts.ready;
    await step("Fits each prompt on one line", async () => {
      for (const [index, scene] of SCENES.entries()) {
        await window.videoThumbnail!.seek(firstFrame((frame) => frame.scene === index));
        const prompt = canvas.getByTestId("prompt");
        await expect(prompt).toHaveTextContent(`Build ${scene.prompt.replaceAll("*", "")}`);
        await expect(prompt.scrollWidth).toBeLessThanOrEqual(prompt.clientWidth);
      }
    });
    await step("Fits each feasibility check in its card", async () => {
      await window.videoThumbnail!.seek(
        firstFrame((frame) => frame.cards.every((card) => card.visible)),
      );
      for (const check of FEASIBILITY_CHECKS) {
        const text = canvas.getByText(check);
        await expect(text).toBeVisible();
        await expect(text.scrollWidth).toBeLessThanOrEqual(text.clientWidth);
      }
    });
  }}
/>

<!-- scripts/render-video-thumbnail.ts steps through this story frame by frame. -->
<Story name="Render" tags={["!test"]} />
