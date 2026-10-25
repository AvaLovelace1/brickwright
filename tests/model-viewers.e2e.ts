import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";
import { ModelViewer } from "./page-objects/ModelViewer";

const COMPARISON = "GPT-6 Astra build without BrickWright";
const PACKED_MODEL = /\.packed\.[\w-]+\.mpd$/;

async function countDraws(page: Page, selector = "canvas") {
  return page.evaluate(async (selector) => {
    const canvases = new Set(document.querySelectorAll(selector));
    if (!canvases.size) throw new Error(`Missing canvas: ${selector}`);
    const prototype = WebGL2RenderingContext.prototype;
    const drawArrays = prototype.drawArrays;
    const drawElements = prototype.drawElements;
    let draws = 0;
    prototype.drawArrays = function (...args) {
      if (canvases.has(this.canvas as HTMLCanvasElement)) draws++;
      return drawArrays.apply(this, args);
    };
    prototype.drawElements = function (...args) {
      if (canvases.has(this.canvas as HTMLCanvasElement)) draws++;
      return drawElements.apply(this, args);
    };
    try {
      for (let frame = 0; frame < 6; frame++) await new Promise(requestAnimationFrame);
      return draws;
    } finally {
      prototype.drawArrays = drawArrays;
      prototype.drawElements = drawElements;
    }
  }, selector);
}

test("models start complete when the visitor prefers reduced motion", async ({
  page,
  mainPage,
}) => {
  const modelDownload = Promise.withResolvers<void>();
  await page.route(/\/lighthouse-sea-serpent\.packed\.[\w-]+\.mpd$/, async (route) => {
    await modelDownload.promise;
    await route.continue();
  });
  await page.emulateMedia({ reducedMotion: "reduce" });
  const viewer = mainPage.viewer();
  try {
    await mainPage.goto();
    await expect(viewer.download).toBeVisible();
    await expect(viewer.steps).toHaveCount(0);
    await expect(viewer.button(/^(Play|Pause|Rewind)$/)).toHaveCount(0);
  } finally {
    modelDownload.resolve();
  }
  await expect(viewer.button("Rewind")).toBeVisible({ timeout: 60_000 });
  await expect(viewer.steps).toHaveAttribute(
    "aria-valuenow",
    (await viewer.steps.getAttribute("aria-valuemax"))!,
  );
});

test("autoplay pauses when the visitor switches on reduced motion", async ({ page, mainPage }) => {
  await mainPage.goto();
  const viewer = mainPage.viewer();
  await expect(viewer.button("Pause")).toBeVisible({ timeout: 60_000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(viewer.button("Play")).toBeVisible();
});

test("comparison models load as their viewers approach the viewport", async ({
  page,
  mainPage,
}) => {
  const requestedModels: string[] = [];
  page.on("request", (request) => {
    if (PACKED_MODEL.test(request.url())) requestedModels.push(new URL(request.url()).pathname);
  });
  await mainPage.goto();
  await expect(mainPage.viewer().button(/^(Pause|Rewind)$/)).toBeVisible({ timeout: 60_000 });
  const comparison = mainPage.viewer(COMPARISON);
  const packedPath = /\/spaceship-gpt-6-astra-without-brickwright\.packed\.[\w-]+\.mpd$/;
  expect(requestedModels.some((path) => packedPath.test(path))).toBe(false);
  await comparison.figure.scrollIntoViewIfNeeded();
  await expect
    .poll(() => requestedModels.some((path) => packedPath.test(path)), { timeout: 60_000 })
    .toBe(true);
  await expect(comparison.button("Rewind")).toBeVisible({ timeout: 60_000 });
});

test("every model viewer links an LDraw file the site serves", async ({ page, mainPage }) => {
  await mainPage.goto();
  const viewers = mainPage.viewers;
  const hrefs = await viewers
    .getByRole("link", { name: "Download LDraw" })
    .evaluateAll((links) => links.map((link) => link.getAttribute("href")!));
  expect(hrefs).toHaveLength(await viewers.count());
  for (const href of hrefs) {
    expect(href).toMatch(/\.ldr$/);
    expect((await page.request.get(href)).ok(), href).toBe(true);
  }
});

test("offscreen sections do not allocate WebGL canvases", async ({ page, mainPage }) => {
  await mainPage.goto();
  await mainPage.viewer().waitUntilLoaded();
  await expect(page.locator("canvas")).toHaveCount(1);
});

test("a dragged carousel build stays inside the carousel", async ({ page, mainPage }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mainPage.goto("experiments");
  const { experiments } = mainPage;
  const slide = experiments.activeSlide;
  for (const figure of await slide.getByRole("figure").all())
    await new ModelViewer(figure).waitUntilLoaded();
  await slide.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
  const carousel = (await experiments.carousel.locator(".swiper").boundingBox())!;
  const build = (await slide.getByRole("figure").last().boundingBox())!;
  // The strip skips the pixel the carousel's edge falls within.
  const outside = {
    x: Math.ceil(carousel.x + carousel.width) + 1,
    y: build.y,
    width: 16,
    height: build.height,
  };
  const before = await page.screenshot({ clip: outside });

  // Dragging right moves the right-hand build partly past the carousel's edge.
  const prompt = (await experiments.prompt.boundingBox())!;
  const y = prompt.y + prompt.height / 2;
  await page.mouse.move(prompt.x + prompt.width * 0.2, y);
  await page.mouse.down();
  try {
    await page.mouse.move(prompt.x + prompt.width * 0.6, y, { steps: 12 });
    await page.evaluate(async () => {
      for (let frame = 0; frame < 2; frame++) await new Promise(requestAnimationFrame);
    });
    expect((await page.screenshot({ clip: outside })).equals(before)).toBe(true);
  } finally {
    await page.mouse.up();
  }
});

test("a stationary viewer redraws for keyboard camera input without rendering continuously", async ({
  page,
  mainPage,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mainPage.goto();
  const viewer = mainPage.viewer();
  await viewer.waitUntilLoaded();
  await viewer.view.focus();
  await expect.poll(() => countDraws(page)).toBe(0);
  const canvas = page.locator("canvas").first();
  const before = await canvas.screenshot();
  await page.keyboard.press("+");
  await expect.poll(async () => (await canvas.screenshot()).equals(before)).toBe(false);
});

test("global rotation respects reduced motion, persists, and controls newly loaded viewers", async ({
  page,
  mainPage,
}) => {
  test.slow();
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mainPage.goto();
  const viewer = mainPage.viewer();
  await viewer.waitUntilLoaded();
  await mainPage.openSettings();
  await expect(mainPage.rotationCheckbox).not.toBeChecked();
  await mainPage.rotationCheckbox.focus();
  await page.keyboard.press("Space");
  await expect(mainPage.rotationCheckbox).toBeChecked();
  await mainPage.closeSettings();
  await expect.poll(() => countDraws(page)).toBeGreaterThan(0);

  await viewer.button("Expand view").click();
  await expect(mainPage.expandedView).toBeVisible();
  await expect.poll(() => countDraws(page, "main canvas")).toBe(0);
  await expect.poll(() => countDraws(page, '[role="dialog"] canvas')).toBeGreaterThan(0);
  await page.keyboard.press("Escape");

  await mainPage.setRotation(false);
  await page.reload();
  await viewer.waitUntilLoaded();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await mainPage.openSettings();
  await expect(mainPage.rotationCheckbox).not.toBeChecked();
  await mainPage.closeSettings();
  await expect.poll(() => countDraws(page)).toBe(0);

  const comparison = mainPage.viewer(COMPARISON);
  await comparison.figure.scrollIntoViewIfNeeded();
  await comparison.waitUntilLoaded();
  await expect.poll(() => countDraws(page), { timeout: 15_000 }).toBe(0);
  await mainPage.setRotation(true);
  await expect.poll(() => countDraws(page)).toBeGreaterThan(0);
});

test("the page remains usable when WebGL is unavailable", async ({ page, mainPage }) => {
  await page.addInitScript(() => {
    const getContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (
      this: HTMLCanvasElement,
      contextId: string,
      options?: unknown,
    ) {
      if (contextId.includes("webgl")) return null;
      return getContext.call(this, contextId as "2d", options);
    } as typeof getContext;
  });
  await mainPage.goto();
  const viewer = mainPage.viewer();
  await expect(viewer.figure.getByRole("alert")).toContainText("Unable to load");
  await expect(viewer.figure).toHaveAttribute("aria-busy", "false");
  await expect(viewer.download).toBeVisible();
  await mainPage.sectionLink("citation").click();
  await expect(page).toHaveURL("/#citation");
});

test("a failed lighting download does not prevent the model from loading", async ({
  page,
  mainPage,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.route(/\.hdr$/, (route) => route.abort());
  await mainPage.goto();
  await mainPage.viewer().waitUntilLoaded();
  expect(errors).toEqual([]);
});
