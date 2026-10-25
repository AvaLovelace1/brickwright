import { expect, type Locator } from "@playwright/test";

export class ModelViewer {
  readonly download: Locator;
  readonly steps: Locator;
  /** The model's drawing area, which exists once the 3D canvas draws the viewer. */
  readonly view: Locator;

  constructor(readonly figure: Locator) {
    this.download = figure.getByRole("link", { name: "Download LDraw" });
    this.steps = figure.getByRole("slider", { name: "Steps shown" });
    this.view = figure.getByRole("group", { name: /interactive 3D view/ });
  }

  button(name: string | RegExp) {
    return this.figure.getByRole("button", { name, exact: true });
  }

  async waitUntilLoaded() {
    await expect(this.figure).toHaveAttribute("aria-busy", "false", { timeout: 60_000 });
  }
}
