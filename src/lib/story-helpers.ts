import { expect, waitFor, within } from "storybook/test";

/** Scrolls a model viewer into view and waits for its model to finish loading. */
export async function waitForModel(figure: HTMLElement) {
  figure.scrollIntoView({ block: "center" });
  await waitFor(() => expect(figure).toHaveAttribute("aria-busy", "false"), { timeout: 45_000 });
}

/** Scrolls a model viewer into view and waits for the 3D canvas to draw it. */
export async function waitForView(figure: HTMLElement) {
  figure.scrollIntoView({ block: "center" });
  await waitFor(
    () =>
      expect(
        within(figure).getByRole("group", { name: /interactive 3D view/ }),
      ).toBeInTheDocument(),
    { timeout: 15_000 },
  );
}

/** Expects a visible viewer's controls to receive clicks above the 3D canvas. */
export function expectControlsAboveCanvas(figure: HTMLElement) {
  const button = within(figure).getByRole("button", { name: "Expand view" });
  const canvases = [...document.querySelectorAll("canvas")];
  // Once canvases accept pointer events, hit testing finds whichever is on top.
  for (const canvas of canvases) canvas.style.pointerEvents = "auto";
  try {
    const { x, y, width, height } = button.getBoundingClientRect();
    const hit = document.elementFromPoint(x + width / 2, y + height / 2);
    expect(button.contains(hit), figure.ariaLabel ?? "").toBe(true);
  } finally {
    for (const canvas of canvases) canvas.style.pointerEvents = "";
  }
}
