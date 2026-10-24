import type { Page } from "@playwright/test";
import { expect, test } from "./fixtures";

async function countDraws(page: Page, selector: string) {
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
  try {
    await mainPage.goto();
    await expect(mainPage.firstModel.getByRole("link", { name: "Download LDraw" })).toBeVisible();
    await expect(mainPage.firstModel.getByRole("slider", { name: "Steps shown" })).toHaveCount(0);
    await expect(
      mainPage.firstModel.getByRole("button", { name: /^(Play|Pause|Rewind)$/ }),
    ).toHaveCount(0);
  } finally {
    modelDownload.resolve();
  }
  await expect(
    mainPage.firstModel.getByRole("button", { name: "Rewind", exact: true }),
  ).toBeVisible({
    timeout: 60_000,
  });
  const slider = mainPage.firstModel.getByRole("slider", { name: "Steps shown" });
  expect(Number(await slider.getAttribute("aria-valuemax"))).toBeGreaterThan(1);
  await expect(slider).toHaveAttribute(
    "aria-valuenow",
    (await slider.getAttribute("aria-valuemax"))!,
  );
});

test("autoplay pauses when the visitor switches on reduced motion", async ({ page, mainPage }) => {
  await mainPage.goto();
  const pause = mainPage.firstModel.getByRole("button", { name: "Pause", exact: true });
  await expect(pause).toBeVisible({ timeout: 60_000 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await expect(
    mainPage.firstModel.getByRole("button", { name: "Play", exact: true }),
  ).toBeVisible();
});

test("comparison models load as their viewers approach the viewport", async ({
  page,
  mainPage,
}) => {
  const requestedModels: string[] = [];
  page.on("request", (request) => {
    if (/\.packed\.[\w-]+\.mpd$/.test(request.url()))
      requestedModels.push(new URL(request.url()).pathname);
  });
  await mainPage.goto();
  await expect(mainPage.firstModel.getByRole("button", { name: /^(Pause|Rewind)$/ })).toBeVisible({
    timeout: 60_000,
  });
  const viewer = page.getByRole("figure", {
    name: "GPT-6 Astra build without BrickWright",
    exact: true,
  });
  const packedPath = /\/spaceship-gpt-6-astra-without-brickwright\.packed\.[\w-]+\.mpd$/;
  expect(requestedModels.some((path) => packedPath.test(path))).toBe(false);
  await viewer.scrollIntoViewIfNeeded();
  await expect
    .poll(() => requestedModels.some((path) => packedPath.test(path)), { timeout: 60_000 })
    .toBe(true);
  const slider = viewer.getByRole("slider", { name: "Steps shown" });
  await expect
    .poll(async () => Number(await slider.getAttribute("aria-valuemax")), { timeout: 60_000 })
    .toBeGreaterThan(1);
  await expect(viewer.getByRole("button", { name: "Rewind", exact: true })).toBeVisible({
    timeout: 60_000,
  });
});

test("every model viewer links an LDraw file the site serves", async ({ page, mainPage }) => {
  await mainPage.goto();
  const viewers = page.locator("figure[aria-busy]");
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
  await mainPage.waitForModel();
  await expect(page.locator("canvas")).toHaveCount(1);
});

test("a stationary viewer redraws for keyboard camera input without rendering continuously", async ({
  page,
  mainPage,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mainPage.goto();
  await mainPage.waitForModel();
  const camera = mainPage.firstModel.getByRole("group", { name: /interactive 3D view/ });
  await camera.focus();
  await expect.poll(() => countDraws(page, "canvas")).toBe(0);
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
  await mainPage.waitForModel();
  await mainPage.openSettings();
  await expect(mainPage.rotationCheckbox).not.toBeChecked();
  await mainPage.rotationCheckbox.focus();
  await page.keyboard.press("Space");
  await expect(mainPage.rotationCheckbox).toBeChecked();
  await mainPage.closeSettings();
  await expect.poll(() => countDraws(page, "canvas")).toBeGreaterThan(0);

  await mainPage.firstModel.getByRole("button", { name: "Expand view" }).click();
  await expect(page.getByRole("dialog", { name: "Expanded model view" })).toBeVisible();
  await expect.poll(() => countDraws(page, "main canvas")).toBe(0);
  await expect.poll(() => countDraws(page, '[role="dialog"] canvas')).toBeGreaterThan(0);
  await page.keyboard.press("Escape");

  await mainPage.openSettings();
  await mainPage.rotationCheckbox.uncheck();
  await mainPage.closeSettings();
  await page.reload();
  await mainPage.waitForModel();
  await page.emulateMedia({ reducedMotion: "no-preference" });
  await mainPage.openSettings();
  await expect(mainPage.rotationCheckbox).not.toBeChecked();
  await mainPage.closeSettings();
  await expect.poll(() => countDraws(page, "canvas")).toBe(0);

  const comparison = page.getByRole("figure", {
    name: "GPT-6 Astra build without BrickWright",
    exact: true,
  });
  await comparison.scrollIntoViewIfNeeded();
  await mainPage.waitForModel(comparison);
  await expect.poll(() => countDraws(page, "canvas"), { timeout: 15_000 }).toBe(0);
  await mainPage.openSettings();
  await mainPage.rotationCheckbox.check();
  await mainPage.closeSettings();
  await expect.poll(() => countDraws(page, "canvas")).toBeGreaterThan(0);
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
  await page.goto("/");
  const viewer = mainPage.firstModel;
  await expect(viewer.getByRole("alert")).toContainText("Unable to load");
  await expect(viewer).toHaveAttribute("aria-busy", "false");
  await expect(viewer.getByRole("link", { name: "Download LDraw" })).toBeVisible();
  await page
    .getByRole("navigation")
    .getByRole("link", { name: /Citation/ })
    .click();
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
  await mainPage.waitForModel();
  expect(errors).toEqual([]);
});
