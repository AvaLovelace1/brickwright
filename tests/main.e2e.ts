import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { MainPage } from "./page-objects/MainPage";
import { CitationPage } from "./page-objects/Citation.ts";

const PAGES = [
  {
    label: "Overview",
    href: "/",
    title: "BrickWright: Agentic Creation of Physically Feasible Brick Builds",
  },
  { label: "Results", href: "/results/", title: "BrickWright ▪ Results" },
  { label: "Acknowledgments", href: "/acknowledgments/", title: "BrickWright ▪ Acknowledgments" },
  { label: "Citation", href: "/citation/", title: "BrickWright ▪ Citation" },
];

test("all pages have appropriate document titles", async ({ page }) => {
  for (const currentPage of PAGES) {
    await page.goto(currentPage.href);
    await expect(page).toHaveTitle(currentPage.title);
  }
});

test("main page contains expected elements", async ({ page }) => {
  const mainPage = new MainPage(page);
  await mainPage.goto();

  await expect(mainPage.header).toBeVisible();
  await expect(mainPage.nav).toBeVisible();
  await expect(mainPage.main).toBeVisible();
  await expect(mainPage.heading).toBeVisible();
  await expect(mainPage.footer).toBeVisible();
});

test("navbar stretches to bottom of viewport", async ({ page }) => {
  const mainPage = new MainPage(page);
  await mainPage.goto();

  const viewportHeight = page.viewportSize()?.height ?? 0;
  const navBox = await mainPage.nav.boundingBox();
  expect(navBox).not.toBeNull();
  expect(navBox!.y + navBox!.height).toBeGreaterThanOrEqual(viewportHeight);
});

test("navbar links navigate to their pages", async ({ page }) => {
  for (const currentPage of PAGES) {
    for (const target of PAGES) {
      await page.goto(currentPage.href);
      const link = page.getByRole("navigation").getByRole("link", { name: target.label });
      await expect(link).toBeVisible();
      await link.click();
      await expect(page).toHaveURL(target.href);
    }
  }
});

test("navbar links work while the LEGO models are still loading", async ({ page }) => {
  await page.goto("/", { waitUntil: "commit" });
  const link = page.getByRole("navigation").getByRole("link", { name: "Results" });
  await link.click({ timeout: 5000 });
  await expect(page).toHaveURL("/results/");
});

test("models on the main page start building themselves", async ({ page }) => {
  await page.goto("/");
  // When a model starts playing, the control turns from "Play" to "Pause", then "Rewind".
  const firstViewer = page.getByRole("figure").first();
  await expect(firstViewer.getByRole("button", { name: "Play" })).toHaveCount(0, {
    timeout: 60_000,
  });
});

test("models do not build themselves when the visitor prefers reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  await expect(page.getByText("Loading model…")).toHaveCount(0, { timeout: 60_000 });
  const firstViewer = page.getByRole("figure").first();
  await expect(firstViewer.getByRole("button", { name: "Play" })).toBeVisible();
});

test("navbar marks only the active page as current", async ({ page }) => {
  for (const currentPage of PAGES) {
    await page.goto(currentPage.href);

    for (const item of PAGES) {
      const link = page.getByRole("navigation").getByRole("link", { name: item.label });
      if (item.href === currentPage.href) {
        await expect(link).toHaveAttribute("aria-current", "page");
      } else {
        await expect(link).not.toHaveAttribute("aria-current");
      }
    }
  }
});

test("all pages have no detectable accessibility violations", async ({ page }) => {
  for (const currentPage of PAGES) {
    await page.goto(currentPage.href);
    const results = await new AxeBuilder({ page }).analyze();
    expect(results.violations).toEqual([]);
  }
});

test("citation copy button works", async ({ page }) => {
  const citationPage = new CitationPage(page);
  await citationPage.goto();
  const citationText = await citationPage.citation.textContent();
  const copyButton = citationPage.copyButton;

  await expect(copyButton).toHaveText("Copy");
  await copyButton.click();
  await expect(copyButton).toHaveText("Copied!");
  await expect(page.evaluate(() => navigator.clipboard.readText())).resolves.toBe(citationText);
  await expect(copyButton).toHaveText("Copy");
});
