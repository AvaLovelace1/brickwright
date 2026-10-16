import { type Locator, type Page } from "@playwright/test";

export class CitationPage {
  readonly page: Page;
  readonly copyButton: Locator;
  readonly citation: Locator;

  constructor(page: Page) {
    this.page = page;
    this.copyButton = page.getByTestId("copy-button");
    this.citation = page.getByTestId("citation");
  }

  async goto() {
    await this.page.goto("/citation");
  }
}
