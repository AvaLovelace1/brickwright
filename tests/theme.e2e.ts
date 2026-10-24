import type { Locator } from "@playwright/test";
import { expect, test } from "./fixtures";
import type { MainPage } from "./page-objects/MainPage";

async function methodColors(mainPage: MainPage) {
  const method = mainPage.section("method");
  const flowchartText = method
    .getByRole("region", { name: "Build creation flowchart" })
    .locator("svg text");
  const success = flowchartText.filter({ hasText: /^(Tests\s*pass|OK)$/ });
  const failure = flowchartText.filter({ hasText: /^(Tests fail|Not OK)$/ });
  const keyword = method
    .locator('[data-token="keyword"]')
    .filter({ hasText: /^import$/ })
    .first();
  await expect(success).toHaveCount(2);
  await expect(failure).toHaveCount(2);
  await expect(keyword).toBeVisible();
  const fills = (texts: Locator) =>
    texts.evaluateAll((elements) => elements.map((el) => getComputedStyle(el).fill));
  return {
    success: await fills(success),
    failure: await fills(failure),
    keyword: await keyword.evaluate((el) => getComputedStyle(el).color),
  };
}

async function referenceThemeColors(mainPage: MainPage) {
  // Fresh Auto renders give the reference palettes that live switching and explicit
  // overrides must reproduce.
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
    const scheme = theme === "Dark" ? "dark" : "light";
    await page.emulateMedia({ colorScheme: scheme === "dark" ? "light" : "dark" });
    await mainPage.selectTheme(theme);
    await page.reload();
    await mainPage.openSettings();
    await expect(mainPage.themeSelect).toHaveAccessibleName(`Theme ${theme}`);
    await mainPage.closeSettings();
    await expect(page.locator("html")).toHaveAttribute("data-theme", scheme);
    await expect(page.locator("html")).toHaveCSS("color-scheme", scheme);
    await expect.poll(() => methodColors(mainPage)).toEqual(colors[scheme]);
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
  await mainPage.openSettings();
  await expect(mainPage.themeSelect).toHaveAccessibleName("Theme Auto");
  await mainPage.closeSettings();
  await expect(page.locator("html")).not.toHaveAttribute("data-theme");
  await page.emulateMedia({ colorScheme: "light" });
  await expect.poll(() => methodColors(mainPage)).toEqual(colors.light);
  const light = await page.locator("body").evaluate((el) => getComputedStyle(el).backgroundColor);
  await page.emulateMedia({ colorScheme: "dark" });
  await expect.poll(() => methodColors(mainPage)).toEqual(colors.dark);
  await expect(page.locator("body")).not.toHaveCSS("background-color", light);
});
