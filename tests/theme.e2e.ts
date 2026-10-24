import { expect, test } from "./fixtures";
import { MainPage } from "./page-objects/MainPage";
import { MethodDemo } from "./page-objects/MethodDemo";

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

test("explicit themes persist across reloads and override the system", async ({
  page,
  mainPage,
}) => {
  const colors = await referenceThemeColors(mainPage);
  for (const theme of ["Dark", "Light"] as const) {
    await page.emulateMedia({ colorScheme: theme === "Dark" ? "light" : "dark" });
    await mainPage.selectTheme(theme);
    await page.reload();
    const settings = await mainPage.openSettings();
    await expect(settings.getByRole("combobox", { name: `Theme ${theme}` })).toBeVisible();
    await mainPage.closeSettings();
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
  const settings = await mainPage.openSettings();
  await expect(settings.getByRole("combobox", { name: "Theme Auto" })).toBeVisible();
  await mainPage.closeSettings();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await page.emulateMedia({ colorScheme: "light" });
  await expectMethodColors(mainPage, colors.light);
  const light = await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await expectMethodColors(mainPage, colors.dark);
  await expect(page.locator("body")).not.toHaveCSS("background-color", light);
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
