import { MethodDemo } from "./page-objects/MethodDemo";
import { expect, type Locator, test as base } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MainPage } from "./page-objects/MainPage";
import { Experiments } from "./page-objects/Experiments.ts";
import { prompts } from "../src/lib/experiment-results.ts";

const test = base.extend<{ mainPage: MainPage }>({
  mainPage: async ({ page }, use) => {
    await use(new MainPage(page));
  },
});

const SECTIONS = ["overview", "motivation", "method", "experiments", "acknowledgments", "citation"];

async function expectCurrentSection(mainPage: MainPage, section: string) {
  await expect(mainPage.sectionLink(section)).toHaveAttribute("aria-current", "location");
  await expect(mainPage.nav.locator("[aria-current]")).toHaveCount(1);
}

async function bottom(locator: Locator) {
  return locator.evaluate((element) => element.getBoundingClientRect().bottom);
}

function methodColorElements(mainPage: MainPage) {
  const method = mainPage.section("method");
  const flowchart = method.getByRole("region", { name: "Build creation flowchart" });
  const success = flowchart.locator("svg text").filter({ hasText: /^(Tests\s*pass|OK)$/ });
  const failure = flowchart.locator("svg text").filter({ hasText: /^(Tests fail|Not OK)$/ });
  const keyword = method
    .locator('[data-token="keyword"]')
    .filter({ hasText: /^import$/ })
    .first();
  return { success, failure, keyword };
}

async function methodColors(mainPage: MainPage) {
  const { success, failure, keyword } = methodColorElements(mainPage);
  await expect(success).toHaveCount(2);
  await expect(failure).toHaveCount(2);
  await expect(keyword).toBeVisible();
  return {
    success: await success.evaluateAll((elements) =>
      elements.map((el) => getComputedStyle(el).fill),
    ),
    failure: await failure.evaluateAll((elements) =>
      elements.map((el) => getComputedStyle(el).fill),
    ),
    keyword: await keyword.evaluate((el) => getComputedStyle(el).color),
  };
}

async function expectMethodColors(
  mainPage: MainPage,
  colors: Awaited<ReturnType<typeof methodColors>>,
) {
  const { success, failure, keyword } = methodColorElements(mainPage);
  for (const [index, color] of colors.success.entries()) {
    await expect(success.nth(index)).toHaveCSS("fill", color);
  }
  for (const [index, color] of colors.failure.entries()) {
    await expect(failure.nth(index)).toHaveCSS("fill", color);
  }
  await expect(keyword).toHaveCSS("color", colors.keyword);
}

async function referenceThemeColors(mainPage: MainPage) {
  // Fresh Auto renders establish the current palettes without pinning design choices.
  // Live switching and explicit overrides must reproduce these same colors.
  await mainPage.page.emulateMedia({ colorScheme: "light" });
  await mainPage.goto("method");
  const light = await methodColors(mainPage);
  await mainPage.page.emulateMedia({ colorScheme: "dark" });
  await mainPage.page.reload();
  const dark = await methodColors(mainPage);
  expect(dark.success).not.toEqual(light.success);
  expect(dark.failure).not.toEqual(light.failure);
  expect(dark.keyword).not.toBe(light.keyword);
  return { light, dark };
}

test("page has a title and no detectable accessibility violations", async ({ page, mainPage }) => {
  await mainPage.goto();
  await expect(page).toHaveTitle(
    "BrickWright: Agentic Creation of Physically Feasible Brick Builds",
  );
  expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
});

test("explicit themes persist across reloads and override the system", async ({
  page,
  mainPage,
}) => {
  const colors = await referenceThemeColors(mainPage);
  for (const theme of ["Dark", "Light"] as const) {
    await page.emulateMedia({ colorScheme: theme === "Dark" ? "light" : "dark" });
    await mainPage.selectTheme(theme);
    await page.reload();
    await expect(page.getByRole("button", { name: `Theme ${theme}` })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme.toLowerCase());
    await expect(page.locator("html")).toHaveCSS("color-scheme", theme.toLowerCase());
    await expectMethodColors(mainPage, colors[theme === "Dark" ? "dark" : "light"]);
  }
});

test("Auto follows live system changes and remains selected after reload", async ({
  page,
  mainPage,
}) => {
  const colors = await referenceThemeColors(mainPage);
  await mainPage.selectTheme("Dark");
  await mainPage.selectTheme("Auto");
  await page.reload();
  await expect(page.getByRole("button", { name: "Theme Auto" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await page.emulateMedia({ colorScheme: "light" });
  await expectMethodColors(mainPage, colors.light);
  const light = await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await expectMethodColors(mainPage, colors.dark);
  await expect(page.locator("body")).not.toHaveCSS("background-color", light);
});

for (const width of [1280, 390]) {
  test(`section navigation and scroll tracking work at ${width}px`, async ({ page, mainPage }) => {
    test.slow();
    await page.setViewportSize({ width, height: 800 });
    await mainPage.goto();
    await test.step("Links jump to visible sections and update the active item", async () => {
      for (const section of SECTIONS) {
        await mainPage.sectionLink(section).click();
        await expect(page).toHaveURL(`/#${section}`);
        await expectCurrentSection(mainPage, section);
        const fixedChrome = width < 768 ? mainPage.nav : mainPage.header;
        await expect
          .poll(
            async () => {
              const top = await mainPage
                .section(section)
                .evaluate((el) => el.getBoundingClientRect().top);
              return top - (await bottom(fixedChrome));
            },
            // Parsing newly visible LDraw builds can temporarily occupy the browser's main thread.
            { timeout: 15_000 },
          )
          .toBeGreaterThanOrEqual(-1);
      }
    });
    await test.step("Scrolling back updates the active item without changing the hash", async () => {
      for (const section of [...SECTIONS].reverse()) {
        await mainPage.section(section).evaluate((el) => el.scrollIntoView());
        await expectCurrentSection(mainPage, section);
      }
      await expect(page).toHaveURL("/#citation");
    });
    await test.step("Direct section links initialize the active item", async () => {
      await mainPage.goto("acknowledgments");
      await expectCurrentSection(mainPage, "acknowledgments");
    });
  });
}

test("navbar links work while the LEGO models are still loading", async ({ page, mainPage }) => {
  await page.goto("/", { waitUntil: "commit" });
  await mainPage.sectionLink("experiments").click({ timeout: 5000 });
  await expect(page).toHaveURL("/#experiments");
});

test("content fits the viewport across mobile and desktop widths", async ({ page, mainPage }) => {
  await mainPage.goto("method");
  const widths = [1280, 1100, 1024, 900, 800, 768, 390];
  const expectFits = async (width: number) => {
    await page.setViewportSize({ width, height: 900 });
    await expect
      .poll(() =>
        page.evaluate(() =>
          Math.max(
            document.documentElement.scrollWidth - window.innerWidth,
            document.querySelector("main")!.getBoundingClientRect().right - window.innerWidth,
          ),
        ),
      )
      .toBeLessThanOrEqual(1);
  };
  for (const width of widths) await expectFits(width);

  const demo = new MethodDemo(page);
  await demo.button("Next step").click();
  await demo.button("Next step").click();
  await expect(demo.source).toBeVisible();
  for (const width of [...widths].reverse()) await expectFits(width);
});

test("models start complete when the visitor prefers reduced motion", async ({
  page,
  mainPage,
}) => {
  const modelDownload = Promise.withResolvers<void>();
  await page.route("**/models/teaser/giant-mushroom-treehouse.packed.mpd", async (route) => {
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

test("comparison models load as their viewers approach the viewport", async ({
  page,
  mainPage,
}) => {
  const requestedModels: string[] = [];
  page.on("request", (request) => {
    if (request.url().endsWith(".packed.mpd"))
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
  const ldr = await viewer.getByRole("link", { name: "Download LDraw" }).getAttribute("href");
  const packedPath = ldr!.replace(/\.ldr$/, ".packed.mpd");
  expect(requestedModels).not.toContain(packedPath);
  await viewer.scrollIntoViewIfNeeded();
  await expect.poll(() => requestedModels, { timeout: 60_000 }).toContain(packedPath);
  const slider = viewer.getByRole("slider", { name: "Steps shown" });
  await expect
    .poll(async () => Number(await slider.getAttribute("aria-valuemax")), { timeout: 60_000 })
    .toBeGreaterThan(1);
  await expect(viewer.getByRole("button", { name: "Rewind", exact: true })).toBeVisible({
    timeout: 60_000,
  });
});

test("Python highlighting follows Auto and explicit themes", async ({ page, mainPage }) => {
  const colors = await referenceThemeColors(mainPage);
  await page.emulateMedia({ colorScheme: "light" });
  await mainPage.goto("method");
  const demo = new MethodDemo(page);
  await demo.button("Next step").click();
  await demo.button("Next step").click();
  await expect(demo.source).toBeVisible();
  const keyword = demo.source
    .locator('[data-token="keyword"]')
    .filter({ hasText: /^import$/ })
    .first();
  await expect(keyword).toHaveCSS("color", colors.light.keyword);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(keyword).toHaveCSS("color", colors.dark.keyword);
  await mainPage.selectTheme("Light");
  await expect(keyword).toHaveCSS("color", colors.light.keyword);
  await page.emulateMedia({ colorScheme: "light" });
  await mainPage.selectTheme("Dark");
  await expect(keyword).toHaveCSS("color", colors.dark.keyword);
});

test("native carousel controls and mobile table scrolling work together on the page", async ({
  page,
}) => {
  test.slow();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/#experiments");
  const results = new Experiments(page);
  const first = `1 / ${prompts.length}`;
  const second = `${(1 % prompts.length) + 1} / ${prompts.length}`;
  const last = `${prompts.length} / ${prompts.length}`;

  const baseline = results.viewers.first();
  await expect(baseline).toHaveAttribute("aria-busy", "false", { timeout: 60_000 });
  await results.drag(baseline);
  await expect(results.progress).toHaveText(first);
  await results.drag(results.prompt);
  await expect(results.progress).toHaveText(second);
  await results.drag(results.prompt, "right");
  await expect(results.progress).toHaveText(first);
  await results.drag(results.prompt, "right");
  await expect(results.progress).toHaveText(last);
  await results.next.click();
  await expect(results.progress).toHaveText(first);
  await results.previous.focus();
  await page.keyboard.press("Enter");
  await expect(results.progress).toHaveText(last);

  await results.tableScroller.focus();
  await expect(results.tableScroller).toBeFocused();
  await results.tableScroller.hover();
  await page.mouse.wheel(600, 0);
  await expect.poll(() => results.tableScroller.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  expect((await new AxeBuilder({ page }).include("#experiments").analyze()).violations).toEqual([]);
});

test("citation copy button works", async ({ page, mainPage }) => {
  await mainPage.goto("citation");
  const citationText = await mainPage.citation.textContent();
  const copyButton = mainPage.copyButton;

  await expect(copyButton).toHaveText("Copy");
  await copyButton.click();
  await expect(copyButton).toHaveText("Copied!");
  await expect(page.evaluate(() => navigator.clipboard.readText())).resolves.toBe(citationText);
  await expect(copyButton).toHaveText("Copy");
});
