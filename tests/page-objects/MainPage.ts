import { expect, type Locator, type Page } from "@playwright/test";

export class MainPage {
  readonly page: Page;
  readonly header: Locator;
  readonly nav: Locator;
  readonly main: Locator;
  readonly firstModel: Locator;
  readonly settings: Locator;
  readonly rotationCheckbox: Locator;

  constructor(page: Page) {
    this.page = page;
    this.header = page.getByRole("banner");
    this.nav = page.getByRole("navigation");
    this.main = page.getByRole("main");
    this.firstModel = this.main.getByRole("figure").first();
    this.settings = page.getByRole("dialog", { name: "Settings", exact: true });
    this.rotationCheckbox = this.settings.getByRole("checkbox", {
      name: "Automatically rotate models",
    });
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

  async selectTheme(theme: "Auto" | "Light" | "Dark") {
    const settings = await this.openSettings();
    await settings.getByRole("combobox", { name: /^Theme / }).click();
    await this.page.getByRole("option", { name: theme, exact: true }).click();
    await this.closeSettings();
  }

  async waitForModel(figure = this.firstModel) {
    await expect(figure).toHaveAttribute("aria-busy", "false", { timeout: 60_000 });
  }

  async openSettings() {
    await this.header.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(this.settings).toBeVisible();
    return this.settings;
  }

  async closeSettings() {
    await this.settings.getByRole("button", { name: "Close settings" }).click();
    await expect(this.settings).toHaveCount(0);
  }
}
