import { type Locator, type Page } from "@playwright/test";

export class MethodDemo {
  readonly figure: Locator;
  readonly source: Locator;

  constructor(page: Page) {
    this.figure = page.getByRole("figure", {
      name: "BrickWright build creation loop",
      exact: true,
    });
    this.source = this.figure.getByLabel("Current build.py source");
  }

  button(name: string) {
    return this.figure.getByRole("button", { name, exact: true });
  }
}
