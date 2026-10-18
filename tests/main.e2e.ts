import { expect, type Locator, test as base } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MainPage } from "./page-objects/MainPage";

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
  await mainPage.goto();
  for (const theme of ["Dark", "Light"] as const) {
    await page.emulateMedia({ colorScheme: theme === "Dark" ? "light" : "dark" });
    await mainPage.selectTheme(theme);
    await page.reload();
    await expect(page.getByRole("button", { name: `Theme ${theme}` })).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", theme.toLowerCase());
    await expect(page.locator("html")).toHaveCSS("color-scheme", theme.toLowerCase());
  }
});

test("Auto follows live system changes and remains selected after reload", async ({
  page,
  mainPage,
}) => {
  await mainPage.goto();
  await mainPage.selectTheme("Dark");
  await mainPage.selectTheme("Auto");
  await page.reload();
  await expect(page.getByRole("button", { name: "Theme Auto" })).toBeVisible();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await page.emulateMedia({ colorScheme: "light" });
  const light = await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect(page.locator("body")).not.toHaveCSS("background-color", light);
});

test("navbar stretches to bottom of viewport", async ({ page, mainPage }) => {
  await mainPage.goto();

  await expect.poll(() => bottom(mainPage.nav)).toBeGreaterThanOrEqual(page.viewportSize()!.height);
});

for (const width of [1280, 390]) {
  test(`section navigation and scroll tracking work at ${width}px`, async ({ page, mainPage }) => {
    await page.setViewportSize({ width, height: 800 });
    await mainPage.goto();
    await test.step("Links jump to visible sections and update the active item", async () => {
      for (const section of SECTIONS) {
        await mainPage.sectionLink(section).click();
        await expect(page).toHaveURL(`/#${section}`);
        await expectCurrentSection(mainPage, section);
        const fixedChrome = width < 768 ? mainPage.nav : mainPage.header;
        await expect
          .poll(async () => {
            const top = await mainPage
              .section(section)
              .evaluate((el) => el.getBoundingClientRect().top);
            return top - (await bottom(fixedChrome));
          })
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

test("main page contains expected elements", async ({ mainPage }) => {
  await mainPage.goto();

  await expect(mainPage.header).toBeVisible();
  await expect(mainPage.nav).toBeVisible();
  await expect(mainPage.main).toBeVisible();
  await expect(mainPage.heading).toBeVisible();
  await expect(mainPage.footer).toBeVisible();
});

test("models on the main page start building themselves", async ({ mainPage }) => {
  await mainPage.goto();
  await expect(mainPage.firstModel.getByRole("button", { name: /^(Pause|Rewind)$/ })).toBeVisible({
    timeout: 60_000,
  });
});

test("models start complete when the visitor prefers reduced motion", async ({
  page,
  mainPage,
}) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await mainPage.goto();
  await expect(
    mainPage.firstModel.getByRole("button", { name: "Rewind", exact: true }),
  ).toBeVisible({
    timeout: 60_000,
  });
  const slider = mainPage.firstModel.getByRole("slider", { name: "Bricks shown" });
  await expect(slider).toHaveAttribute(
    "aria-valuenow",
    (await slider.getAttribute("aria-valuemax"))!,
  );
  await mainPage.firstModel.getByRole("button", { name: "Rewind", exact: true }).click();
  await expect(slider).toHaveAttribute("aria-valuenow", "1");
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
  const slider = viewer.getByRole("slider", { name: "Bricks shown" });
  await expect
    .poll(async () => Number(await slider.getAttribute("aria-valuemax")), { timeout: 60_000 })
    .toBeGreaterThan(1);
  await expect(viewer.getByRole("button", { name: "Rewind", exact: true })).toBeVisible({
    timeout: 60_000,
  });
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
