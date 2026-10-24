import { expect, waitFor } from "storybook/test";

/** Scrolls a model viewer into view and waits for its model to finish loading. */
export async function waitForModel(figure: HTMLElement) {
  figure.scrollIntoView({ block: "center" });
  await waitFor(() => expect(figure).toHaveAttribute("aria-busy", "false"), { timeout: 45_000 });
}
