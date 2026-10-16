import { type Locator, type Page } from "@playwright/test";

export class MainPage {
  readonly page: Page;
  readonly header: Locator;
  readonly nav: Locator;
  readonly main: Locator;
  readonly heading: Locator;
  readonly footer: Locator;

  constructor(page: Page) {
    this.page = page;
    this.header = page.getByRole("banner");
    this.nav = page.getByRole("navigation");
    this.main = page.getByRole("main");
    this.heading = this.main.getByRole("heading");
    this.footer = page.getByRole("contentinfo");
  }

  async goto() {
    await this.page.goto("/");
  }
}
