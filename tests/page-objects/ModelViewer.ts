import { expect, type Locator } from "@playwright/test";

export class ModelViewer {
  readonly download: Locator;
  readonly steps: Locator;

  constructor(readonly figure: Locator) {
    this.download = figure.getByRole("link", { name: "Download LDraw" });
    this.steps = figure.getByRole("slider", { name: "Steps shown" });
  }

  button(name: string | RegExp) {
    return this.figure.getByRole("button", { name, exact: true });
  }

  async waitUntilLoaded() {
    await expect(this.figure).toHaveAttribute("aria-busy", "false", { timeout: 60_000 });
  }
}
