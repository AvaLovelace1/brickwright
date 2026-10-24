import AxeBuilder from "@axe-core/playwright";
import type { Locator } from "@playwright/test";
import { expect, test } from "./fixtures";
import { MainPage } from "./page-objects/MainPage";
import { MethodDemo } from "./page-objects/MethodDemo";
import { Experiments } from "./page-objects/Experiments";
import { prompts } from "../src/lib/experiment-results";

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

test("the narrow mobile page has no detectable WCAG accessibility violations", async ({ page }) => {
  await page.setViewportSize({ width: 320, height: 844 });
  await page.goto("/#method");
  const { violations } = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
    .analyze();
  expect(violations).toEqual([]);
});

test("author names link to their homepages", async ({ mainPage }) => {
  await mainPage.goto();
  const author = mainPage.section("overview").getByRole("link", { name: "Ava Pun", exact: true });
  await expect(author).toHaveAttribute("href", /^https:\/\//);
  await expect(author).toHaveAttribute("target", "_blank");
  await expect(author).toHaveAttribute("rel", "external noopener");
});

test("keyboard users can skip navigation", async ({ page, browserName }) => {
  await page.goto("/");
  // Safari on macOS uses Option-Tab to include links in keyboard navigation.
  await page.keyboard.press(
    browserName === "webkit" && process.platform === "darwin" ? "Alt+Tab" : "Tab",
  );
  const skip = page.getByRole("link", { name: "Skip to content" });
  await expect(skip).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("main")).toBeFocused();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          document.querySelector("main")!.getBoundingClientRect().top -
          document.querySelector("header")!.getBoundingClientRect().bottom,
      ),
    )
    .toBeGreaterThanOrEqual(-1);
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
  const widths = [1280, 1100, 1024, 900, 800, 768, 390, 320];
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
