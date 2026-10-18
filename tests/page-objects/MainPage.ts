import { type Locator, type Page } from "@playwright/test";

export class MainPage {
  readonly page: Page;
  readonly header: Locator;
  readonly nav: Locator;
  readonly main: Locator;
  readonly firstModel: Locator;
  readonly citation: Locator;
  readonly copyButton: Locator;

  constructor(page: Page) {
    this.page = page;
    this.header = page.getByRole("banner");
    this.nav = page.getByRole("navigation");
    this.main = page.getByRole("main");
    this.firstModel = this.main.getByRole("figure").first();
    this.citation = this.main.getByTestId("citation");
    this.copyButton = this.section("citation").getByRole("button", { name: /^(Copy|Copied!)$/ });
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
    await this.page.getByRole("button", { name: /^Theme / }).click();
    await this.page.getByRole("option", { name: theme, exact: true }).click();
  }
}
