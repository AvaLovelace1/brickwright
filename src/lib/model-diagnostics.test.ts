import { expect, test } from "vitest";
import { isPhysicallyValid, loadDiagnostics, type ModelDiagnostics } from "./model-diagnostics";

const diagnostics: ModelDiagnostics = {
  version: 1,
  coordinateSystem: "ldraw",
  units: "LDU",
  placements: [],
  floating: ["floating"],
  collisions: [["first", "second"]],
  intersectionPositions: [],
};

test.each([
  { condition: "separate grounded components", collisions: [], floating: [], valid: true },
  { condition: "collisions", collisions: diagnostics.collisions, floating: [], valid: false },
  { condition: "floating parts", collisions: [], floating: diagnostics.floating, valid: false },
  {
    condition: "collisions and floating parts",
    collisions: diagnostics.collisions,
    floating: diagnostics.floating,
    valid: false,
  },
])("physical validity with $condition", ({ collisions, floating, valid }) => {
  const report = { collisions, floating, components: 2 };
  expect(isPhysicallyValid(report)).toBe(valid);
});

test("loads valid diagnostic data", async () => {
  const url = `data:application/json,${encodeURIComponent(JSON.stringify(diagnostics))}`;
  await expect(loadDiagnostics(url)).resolves.toEqual(diagnostics);
});
