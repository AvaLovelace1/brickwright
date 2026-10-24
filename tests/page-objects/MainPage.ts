import { expect, type Locator, type Page } from "@playwright/test";
import { Experiments } from "./Experiments";
import { MethodDemo } from "./MethodDemo";
import { ModelViewer } from "./ModelViewer";

export class MainPage {
  readonly header: Locator;
  readonly nav: Locator;
  readonly main: Locator;
  readonly settings: Locator;
  readonly themeSelect: Locator;
  readonly rotationCheckbox: Locator;
  readonly methodDemo: MethodDemo;
  readonly experiments: Experiments;

  constructor(readonly page: Page) {
    this.header = page.getByRole("banner");
    this.nav = page.getByRole("navigation");
    this.main = page.getByRole("main");
    this.settings = page.getByRole("dialog", { name: "Settings", exact: true });
    this.themeSelect = this.settings.getByRole("combobox", { name: /^Theme / });
    this.rotationCheckbox = this.settings.getByRole("checkbox", {
      name: "Automatically rotate models",
    });
    this.methodDemo = new MethodDemo(page);
    this.experiments = new Experiments(page);
  }

  async goto(section?: string) {
    await this.page.goto(section ? `/#${section}` : "/");
  }

  section(id: string) {
    return this.main.getByRole("region", { name: new RegExp(`^${id}$`, "i") });
  }

  sectionLink(id: string) {
    return this.nav.getByRole("link", { name: new RegExp(`\\b${id}$`, "i") });
  }

  viewer(name?: string) {
    return new ModelViewer(
      name
        ? this.main.getByRole("figure", { name, exact: true })
        : this.main.getByRole("figure").first(),
    );
  }

  async openSettings() {
    await this.header.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(this.settings).toBeVisible();
  }

  async closeSettings() {
    await this.settings.getByRole("button", { name: "Close settings" }).click();
    await expect(this.settings).toHaveCount(0);
  }

  async selectTheme(theme: "Auto" | "Light" | "Dark") {
    await this.openSettings();
    await this.themeSelect.click();
    await this.page.getByRole("option", { name: theme, exact: true }).click();
    await this.closeSettings();
  }

  async setRotation(enabled: boolean) {
    await this.openSettings();
    await this.rotationCheckbox.setChecked(enabled);
    await this.closeSettings();
  }

  async expectCurrentSection(id: string) {
    await expect(this.sectionLink(id)).toHaveAttribute("aria-current", "location");
    await expect(this.nav.locator("[aria-current]")).toHaveCount(1);
  }

  async expectBelowChrome(target: Locator, chrome = this.header) {
    await expect
      .poll(
        async () =>
          (await target.evaluate((el) => el.getBoundingClientRect().top)) -
          (await chrome.evaluate((el) => el.getBoundingClientRect().bottom)),
        // Parsing newly visible LDraw builds can temporarily occupy the browser's main thread.
        { timeout: 15_000 },
      )
      .toBeGreaterThanOrEqual(-1);
  }
}
