import { expect, test } from "vitest";
import { isPhysicallyValid, loadDiagnostics } from "./model-diagnostics";

const collisions: [string, string][] = [["first", "second"]];
const floating = ["floating"];

test.each([
  { condition: "separate grounded components", collisions: [], floating: [], valid: true },
  { condition: "collisions", collisions, floating: [], valid: false },
  { condition: "floating parts", collisions: [], floating, valid: false },
  { condition: "collisions and floating parts", collisions, floating, valid: false },
])("physical validity with $condition", ({ collisions, floating, valid }) => {
  expect(isPhysicallyValid({ collisions, floating })).toBe(valid);
});

test("loads diagnostics with intersection positions as a typed array", async () => {
  const data = { placements: [], floating, collisions, intersectionPositions: [1, 2, 3, 4, 5, 6] };
  const url = `data:application/json,${encodeURIComponent(JSON.stringify(data))}`;
  await expect(loadDiagnostics(url)).resolves.toEqual({
    ...data,
    intersectionPositions: new Float32Array(data.intersectionPositions),
  });
});
