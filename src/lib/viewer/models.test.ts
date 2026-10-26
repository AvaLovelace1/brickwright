import { createHash } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import { expect, test } from "vitest";
import { Box3, Vector3 } from "three";
import { createLoader, parsePackedModel } from "./ldraw";
import { matchDiagnosticPlacements } from "./model-diagnostic-view";
import { createModel, modelFiles } from "./models";

const MODEL_DIRECTORY = "src/lib/assets/models/";
const files = await readdir(MODEL_DIRECTORY, { recursive: true });
const models = files.filter((file) => file.endsWith(".ldr")).map((file) => file.slice(0, -4));

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
  expect(modelFiles("teaser/poseable-crab")).toEqual({
    ldr: expect.stringContaining("poseable-crab.ldr"),
    ldrPacked: expect.stringContaining("poseable-crab.packed.mpd"),
    diagnosticsUrl: undefined,
  });
});

test.each(models)(
  "committed model has a packed copy with nonempty bounds and matching diagnostics: %s",
  async (model) => {
    const path = MODEL_DIRECTORY + model;
    // Placements and bounds ignore normals.
    const loader = createLoader({ smoothNormals: false });
    const group = await parsePackedModel(loader, await readFile(`${path}.packed.mpd`, "utf8"));
    const size = Math.max(...new Box3().setFromObject(group).getSize(new Vector3()).toArray());
    expect(Number.isFinite(size) && size > 0).toBe(true);

    if (!files.includes(`${model}.diagnostics.json`)) return;
    const diagnostics = JSON.parse(await readFile(`${path}.diagnostics.json`, "utf8"));
    expect(diagnostics).toMatchObject({ version: 1, coordinateSystem: "ldraw", units: "LDU" });
    const ldraw = await readFile(`${path}.ldr`);
    expect(createHash("sha256").update(ldraw).digest("hex")).toBe(diagnostics.modelSha256);
    expect(matchDiagnosticPlacements(group, diagnostics).size).toBe(diagnostics.placements.length);
  },
  60_000,
);
