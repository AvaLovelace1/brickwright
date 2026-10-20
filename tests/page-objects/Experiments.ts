import type { Locator, Page } from "@playwright/test";

export class Experiments {
  readonly section: Locator;
  readonly carousel: Locator;
  readonly progress: Locator;
  readonly previous: Locator;
  readonly next: Locator;
  readonly prompt: Locator;
  readonly viewers: Locator;
  readonly tableScroller: Locator;

  constructor(private readonly page: Page) {
    this.section = page.getByRole("region", { name: "Experiments", exact: true });
    this.carousel = this.section.getByRole("region", { name: "Qualitative comparison" });
    this.progress = this.carousel.getByRole("status", { name: "Prompt position" });
    this.previous = this.carousel.getByRole("button", { name: "Previous prompt" });
    this.next = this.carousel.getByRole("button", { name: "Next prompt" });
    // Swiper owns slide order and active classes; keep that integration detail in one place.
    const activeSlide = this.carousel.locator(".swiper-slide-active");
    this.prompt = activeSlide.locator("p").first();
    this.viewers = activeSlide.getByRole("figure");
    this.tableScroller = this.section.getByRole("region", { name: "Quantitative results" });
  }

  async drag(target: Locator, direction: "left" | "right" = "left") {
    // Center the target so the fixed header cannot intercept the drag.
    await target.evaluate((el) => el.scrollIntoView({ block: "center", behavior: "instant" }));
    const box = (await target.boundingBox())!;
    const [start, end] = direction === "left" ? [0.8, 0.2] : [0.2, 0.8];
    const y = box.y + box.height / 2;
    await this.page.mouse.move(box.x + box.width * start, y);
    await this.page.mouse.down();
    await this.page.mouse.move(box.x + box.width * end, y, { steps: 12 });
    await this.page.mouse.up();
  }
}
