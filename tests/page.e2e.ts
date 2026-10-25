import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "./fixtures";
import { prompts } from "../src/lib/experiment-results";

const SITE_URL = "https://avalovelace1.github.io/brickwright/";
const SECTIONS = ["overview", "motivation", "method", "experiments", "acknowledgments", "citation"];

test(
  "page has a title and no detectable accessibility violations",
  { tag: "@a11y" },
  async ({ page, mainPage }) => {
    await mainPage.goto();
    await expect(page).toHaveTitle(
      "BrickWright: Agentic Creation of Physically Feasible Brick Builds",
    );
    expect((await new AxeBuilder({ page }).analyze()).violations).toEqual([]);
  },
);

test("page describes itself to search engines and link previews", async ({ page, mainPage }) => {
  await mainPage.goto();
  const meta = (selector: string) => page.locator(`head meta[${selector}]`);
  const description = await meta('name="description"').getAttribute("content");
  expect(description).toContain("physically feasible");
  await expect(meta('property="og:title"')).toHaveAttribute("content", await page.title());
  await expect(meta('property="og:description"')).toHaveAttribute("content", description!);
  await expect(meta('property="og:type"')).toHaveAttribute("content", "website");
  await expect(meta('name="twitter:card"')).toHaveAttribute("content", "summary_large_image");
  await expect(meta('name="author"')).toHaveAttribute("content", /^Ava Pun, .*Jun-Yan Zhu$/);
  await expect(page.locator('head link[rel="canonical"]')).toHaveAttribute("href", SITE_URL);
  await expect(meta('property="og:url"')).toHaveAttribute("content", SITE_URL);
  const image = await meta('property="og:image"').getAttribute("content");
  expect(image).toMatch(new RegExp(`^${SITE_URL}`));
  // The site deploys under SITE_URL, so the image's path within it is served locally too.
  const response = await page.request.get(image!.slice(SITE_URL.length - 1));
  expect(response.headers()["content-type"]).toBe("image/png");
  await expect(meta('property="og:image:alt"')).toHaveAttribute("content", /lighthouse/);
});

test(
  "the narrow mobile page has no detectable WCAG accessibility violations",
  { tag: "@a11y" },
  async ({ page, mainPage }) => {
    await page.setViewportSize({ width: 320, height: 844 });
    await mainPage.goto("method");
    const { violations } = await new AxeBuilder({ page })
      .withTags(["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"])
      .analyze();
    expect(violations).toEqual([]);
  },
);

test("keyboard users can skip navigation", async ({ page, mainPage, browserName }) => {
  await mainPage.goto();
  // Safari on macOS uses Option-Tab to include links in keyboard navigation.
  await page.keyboard.press(
    browserName === "webkit" && process.platform === "darwin" ? "Alt+Tab" : "Tab",
  );
  await expect(page.getByRole("link", { name: "Skip to content" })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(mainPage.main).toBeFocused();
  await mainPage.expectBelowChrome(mainPage.main);
});

for (const width of [1280, 390]) {
  test(`section navigation and scroll tracking work at ${width}px`, async ({ page, mainPage }) => {
    test.slow();
    await page.setViewportSize({ width, height: 800 });
    await mainPage.goto();
    const fixedChrome = width < 768 ? mainPage.nav : mainPage.header;
    await test.step("Links jump to visible sections and update the active item", async () => {
      for (const section of SECTIONS) {
        await mainPage.sectionLink(section).click();
        await expect(page).toHaveURL(`/#${section}`);
        await mainPage.expectCurrentSection(section);
        await mainPage.expectBelowChrome(mainPage.section(section), fixedChrome);
      }
    });
    await test.step("Scrolling back updates the active item without changing the hash", async () => {
      for (const section of [...SECTIONS].reverse()) {
        await mainPage.section(section).evaluate((el) => el.scrollIntoView());
        await mainPage.expectCurrentSection(section);
      }
      await expect(page).toHaveURL("/#citation");
    });
    await test.step("Direct section links initialize the active item", async () => {
      await mainPage.goto("acknowledgments");
      await mainPage.expectCurrentSection("acknowledgments");
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

  const demo = mainPage.methodDemo;
  await demo.button("Next step").click();
  await demo.button("Next step").click();
  await expect(demo.source).toBeVisible();
  for (const width of [...widths].reverse()) await expectFits(width);
});

test(
  "native carousel controls and mobile table scrolling work together on the page",
  { tag: "@a11y" },
  async ({ page, mainPage }) => {
    test.slow();
    await page.setViewportSize({ width: 390, height: 844 });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await mainPage.goto("experiments");
    const { experiments } = mainPage;

    await experiments.viewer.waitUntilLoaded();
    await experiments.drag(experiments.viewer.figure);
    await expect(experiments.progress).toHaveText(experiments.position(1));
    await experiments.drag(experiments.prompt);
    await expect(experiments.progress).toHaveText(experiments.position(2));
    await experiments.drag(experiments.prompt, "right");
    await expect(experiments.progress).toHaveText(experiments.position(1));
    await experiments.drag(experiments.prompt, "right");
    await expect(experiments.progress).toHaveText(experiments.position(prompts.length));
    await experiments.next.click();
    await expect(experiments.progress).toHaveText(experiments.position(1));
    await experiments.previous.focus();
    await page.keyboard.press("Enter");
    await expect(experiments.progress).toHaveText(experiments.position(prompts.length));

    const { tableScroller } = experiments;
    await tableScroller.focus();
    await expect(tableScroller).toBeFocused();
    await tableScroller.hover();
    await page.mouse.wheel(600, 0);
    await expect.poll(() => tableScroller.evaluate((el) => el.scrollLeft)).toBeGreaterThan(0);
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
    ).toBe(true);
    expect((await new AxeBuilder({ page }).include("#experiments").analyze()).violations).toEqual(
      [],
    );
  },
);
