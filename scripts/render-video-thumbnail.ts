/**
 * Renders the Hugging Face paper thumbnail video from the "Content/Video Thumbnail" story, by
 * stepping it frame by frame in headless Chromium and encoding the screenshots with ffmpeg. The
 * soundtrack is downloaded separately, as the README describes.
 *
 * Usage: node scripts/render-video-thumbnail.ts [output.mp4]
 */
import { spawn } from "node:child_process";
import { once } from "node:events";
import { existsSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const OUT = process.argv[2] ?? "video-thumbnail.mp4";
const DEVICE_SCALE_FACTOR = 2;
const PORT = 6007;
const STORY_URL = `http://localhost:${PORT}/iframe.html?id=content-video-thumbnail--render&viewMode=story`;
const SOUNDTRACK = fileURLToPath(
  new URL("./Daniel Levi - That's What Makes It Right [NCS Release].mp3", import.meta.url),
);
// Seconds. The song's ending closes the video, and its entrance fades in.
const FADE_IN = 1;

if (!existsSync(SOUNDTRACK)) throw new Error(`Missing soundtrack ${SOUNDTRACK}; see the README`);

const storybook = spawn("npx", ["storybook", "dev", "-p", String(PORT), "--ci", "--no-open"], {
  stdio: "ignore",
  detached: true,
});

async function waitForStorybook() {
  for (let attempt = 0; attempt < 240; attempt++) {
    if (storybook.exitCode !== null) throw new Error("Storybook exited before it started serving");
    if ((await fetch(STORY_URL).catch(() => undefined))?.ok) return;
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Storybook did not start serving at ${STORY_URL}`);
}

const browser = await chromium.launch({ channel: "chromium" });
try {
  await waitForStorybook();
  const page = await browser.newPage({ deviceScaleFactor: DEVICE_SCALE_FACTOR });
  page.on("pageerror", (error) => console.error(error));
  await page.goto(STORY_URL);
  await page.waitForFunction(() => window.videoThumbnail, undefined, { timeout: 120_000 });
  const { duration, fps } = await page.evaluate(async () => {
    const { duration, fps, ready } = window.videoThumbnail!;
    await ready;
    return { duration, fps };
  });
  const clip = (await page.locator("section").boundingBox())!;
  // The encoder emits whole frames, so the song is aligned to the output's duration.
  const frames = Math.round(duration * fps);
  const outputDuration = frames / fps;
  const ffmpeg = spawn(
    "ffmpeg",
    // prettier-ignore
    [
      "-y", "-loglevel", "error",
      "-f", "image2pipe", "-framerate", String(fps), "-c:v", "png", "-i", "-",
      "-sseof", `-${outputDuration}`, "-i", SOUNDTRACK,
      "-filter:a", `atrim=duration=${outputDuration},afade=t=in:st=0:d=${FADE_IN}`,
      "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
      "-c:a", "aac", "-b:a", "192k", "-map", "0:v:0", "-map", "1:a:0", "-shortest",
      "-movflags", "+faststart",
      OUT,
    ],
    { stdio: ["pipe", "inherit", "inherit"] },
  );
  for (let frame = 0; frame < frames; frame++) {
    await page.evaluate((time) => window.videoThumbnail!.seek(time), frame / fps);
    if (!ffmpeg.stdin.write(await page.screenshot({ clip }))) await once(ffmpeg.stdin, "drain");
    if (frame % fps === 0) process.stdout.write(`\rRendered ${frame}/${frames} frames`);
  }
  ffmpeg.stdin.end();
  const [code] = await once(ffmpeg, "close");
  if (code !== 0) throw new Error(`ffmpeg exited with code ${code}`);
  console.log(`\rRendered ${frames} frames to ${OUT}`);
} finally {
  await browser.close();
  process.kill(-storybook.pid!);
}
