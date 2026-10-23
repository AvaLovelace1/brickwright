import { readdir } from "node:fs/promises";
import { expect, test } from "vitest";
import { createModel } from "./models";

const modelDirectory = "src/lib/assets/models/";

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
  first.status = "loaded";
  expect(second.stepsShown).toBe(1);
  expect(second.status).toBe("idle");
  expect(second.caption).toBe("Second view");
  expect(second.ldrPacked).toBe(first.ldrPacked);
});

test("allows models without diagnostics", () => {
  expect(createModel("teaser/poseable-crab", "Crab").diagnosticsUrl).toBeUndefined();
});

test("every committed LDraw model has a packed copy for the viewer", async () => {
  const files = await readdir(modelDirectory, { recursive: true });
  const unpacked = files.filter(
    (file) =>
      file.endsWith(".ldr") &&
      !file.startsWith("test-examples/") &&
      !files.includes(file.replace(/\.ldr$/, ".packed.mpd")),
  );
  expect(unpacked).toEqual([]);
});
