import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import { expect, test } from "vitest";
import { demoSteps, methodBuilds, type BuildRevision } from "./method";

const readDiagnostics = async (revision: string) =>
  JSON.parse(
    await readFile(`src/lib/assets/models/method/house-${revision}.diagnostics.json`, "utf8"),
  );

test("the first validation fails only on collisions, and later validations pass every check", () => {
  const failedChecks = demoSteps.flatMap((step) =>
    step.result?.kind === "validation"
      ? [step.result.checks.filter((check) => !check.passed).map((check) => check.label)]
      : [],
  );
  expect(failedChecks).toEqual([["No collisions"], [], []]);
});

test("build revisions change when the agent writes or edits the file", () => {
  let currentRevision: BuildRevision | null = null;
  for (const step of demoSteps) {
    if (step.stage === "write") {
      expect(step.revision).not.toBe(currentRevision);
      expect(step.call).toMatch(/^(write_build|edit_build)\(/);
      if (currentRevision && step.revision) {
        const args = step.call?.match(/^edit_build\((.*)\)$/)?.[1];
        expect(args).toBeDefined();
        const [before, after] = JSON.parse(`[${args}]`);
        expect(methodBuilds[currentRevision].source.replace(before, after)).toBe(
          methodBuilds[step.revision].source,
        );
      }
      currentRevision = step.revision;
    }
    expect(step.revision).toBe(currentRevision);
    if (step.result?.kind === "render") expect(step.result.revision).toBe(currentRevision);
  }
  expect(currentRevision).toBe("final");
});

test("the method example repairs a low roof while retaining twenty connected, grounded parts", async () => {
  for (const [revision, build] of Object.entries(methodBuilds)) {
    const data = await readDiagnostics(revision);
    expect(data.placements).toHaveLength(20);
    expect(data.floating).toEqual([]);
    expect(data.components).toBe(1);
    expect(data.collisions).toHaveLength(revision === "draft1" ? 27 : 0);
    if (revision === "draft1") expect(data.intersectionPositions.length).toBeGreaterThan(0);
    else expect(data.intersectionPositions).toEqual([]);
    expect(build.report.brick_count).toBe(20);
    expect(build.report.ok).toBe(revision !== "draft1");
    expect(createHash("sha256").update(build.source).digest("hex")).toBe(data.sourceSha256);
  }
});

test("the collision repair raises the eaves and roof by one brick", async () => {
  const draft = await readDiagnostics("draft1");
  const repaired = await readDiagnostics("draft2");
  const movedParts: string[] = [];
  for (const [index, placement] of draft.placements.entries()) {
    const next = repaired.placements[index];
    expect(next.part).toBe(placement.part);
    expect(next.rotation).toEqual(placement.rotation);
    if (placement.position.some((value: number, axis: number) => value !== next.position[axis])) {
      movedParts.push(placement.part);
      // One brick is 24 LDU, with upward motion negative on LDraw's Y axis.
      expect(next.position).toEqual([
        placement.position[0],
        placement.position[1] - 24,
        placement.position[2],
      ]);
    }
  }
  expect(movedParts.sort()).toEqual([
    "3032.dat",
    "3032.dat",
    "3038.dat",
    "3038.dat",
    "3038.dat",
    "3038.dat",
    "3795.dat",
  ]);
});
