import { expect, test } from "vitest";
import { createModel } from "./models";

test("creates independent viewer state for the same model assets", () => {
  const first = createModel("method/house-draft1", "First view");
  const second = createModel("method/house-draft1", "Second view");
  expect(first).toMatchObject({
    caption: "First view",
    stepsShown: 1,
    maxSteps: 1,
    ldr: expect.stringContaining("house-draft1.ldr"),
    ldrPacked: expect.stringContaining("house-draft1.packed.mpd"),
    diagnosticsUrl: expect.stringContaining("house-draft1.diagnostics.json"),
  });
  first.stepsShown = 10;
  first.loaded = true;
  expect(second.stepsShown).toBe(1);
  expect(second.loaded).toBeUndefined();
  expect(second.caption).toBe("Second view");
  expect(second.ldrPacked).toBe(first.ldrPacked);
});

test("allows models without diagnostics and rejects missing geometry", () => {
  expect(createModel("teaser/poseable-crab", "Crab").diagnosticsUrl).toBeUndefined();
  expect(() => createModel("missing", "Missing")).toThrow("Missing model assets: missing");
});
