import { test as base } from "@playwright/test";
import { MainPage } from "./page-objects/MainPage";

export { expect } from "@playwright/test";

export const test = base.extend<{ mainPage: MainPage }>({
  mainPage: async ({ page }, use) => {
    await use(new MainPage(page));
  },
});
