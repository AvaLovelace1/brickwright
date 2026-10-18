import { readFile } from "node:fs/promises";
import { createHash } from "node:crypto";
import { expect, test } from "vitest";
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, Vector3 } from "three";
import { LDrawLoader } from "three/examples/jsm/loaders/LDrawLoader.js";
import { LDrawConditionalLineMaterial } from "three/addons/materials/LDrawConditionalLineMaterial.js";
import { parsePackedModel } from "./ldraw";
import {
  createDiagnosticView,
  matchDiagnosticPlacements,
  type ModelDiagnostics,
} from "./model-diagnostics";

const identity = [1, 0, 0, 0, 1, 0, 0, 0, 1];
const diagnostics: ModelDiagnostics = {
  version: 1,
  coordinateSystem: "ldraw",
  units: "LDU",
  placements: [
    { id: "floating", part: "brick.dat", position: [30, 0, 0], rotation: identity },
    { id: "valid", part: "brick.dat", position: [10, 0, 0], rotation: identity },
    { id: "colliding", part: "brick.dat", position: [20, 0, 0], rotation: identity },
    { id: "colliding2", part: "brick.dat", position: [40, 0, 0], rotation: identity },
  ],
  floating: ["floating"],
  collisions: [["colliding", "colliding2"]],
  intersectionPositions: [20, 0, 0, 21, 1, 0],
};

function createModel() {
  const model = new Group();
  const assembly = new Group();
  assembly.position.x = 10;
  model.add(assembly);
  const material = new MeshStandardMaterial({ opacity: 0.6, transparent: true });
  const meshes = [0, 10, 20, 30].map((x) => {
    const part = new Group();
    part.name = "parts/brick.dat";
    part.position.x = x;
    const mesh = new Mesh(new BoxGeometry(), material);
    part.add(mesh);
    assembly.add(part);
    return mesh;
  });
  return { model, meshes, material };
}

test("matches nested part placements by identity and transform, not diagnostic order", () => {
  const { model, meshes } = createModel();
  model.rotation.x = Math.PI;
  model.scale.setScalar(0.01);
  model.position.set(1, 2, 3);
  const parts = matchDiagnosticPlacements(model, diagnostics);
  expect(parts.get("valid")).toBe(meshes[0].parent);
  expect(parts.get("colliding")).toBe(meshes[1].parent);
  expect(parts.get("floating")).toBe(meshes[2].parent);
});

test("highlights colliding and floating bricks independently from intersection visibility", () => {
  const { model, meshes, material } = createModel();
  const otherViewer = model.clone();
  const view = createDiagnosticView(model, diagnostics);
  view.update({ highlightInvalid: true, showIntersections: false });
  expect(meshes[0].material.opacity).toBeLessThan(0.6);
  expect(meshes[1].material.opacity).toBe(1);
  expect(meshes[2].material.opacity).toBe(1);
  expect(meshes[3].material.opacity).toBe(1);
  expect(material.opacity).toBe(0.6);
  expect((otherViewer.children[0].children[0].children[0] as Mesh).material).toBe(material);
  expect(view.intersections.visible).toBe(false);

  view.update({ highlightInvalid: false, showIntersections: true });
  expect(meshes.map((mesh) => mesh.material)).toEqual([material, material, material, material]);
  expect(view.intersections.visible).toBe(true);
  view.dispose();
});

test("intersection lines use the same transform as the model without becoming build steps", () => {
  const { model } = createModel();
  model.rotation.set(Math.PI, 0.5, 0);
  model.scale.setScalar(0.02);
  model.position.set(1, 2, 3);
  const steps = model.children.length;
  const view = createDiagnosticView(model, diagnostics);
  const positions = view.intersections.geometry.getAttribute("position");
  view.intersections.updateMatrixWorld();
  const point = new Vector3()
    .fromBufferAttribute(positions, 0)
    .applyMatrix4(view.intersections.matrixWorld);
  const expected = new Vector3(20, 0, 0).applyMatrix4(model.matrixWorld);
  expect(point.distanceTo(expected)).toBeLessThan(1e-6);
  expect(model.children).toHaveLength(steps);
  expect(positions.count).toBe(2);
  view.dispose();
});

test("restores original materials when a diagnostic view is disposed", () => {
  const { model, meshes, material } = createModel();
  const view = createDiagnosticView(model, diagnostics);
  view.update({ highlightInvalid: true, showIntersections: true });
  view.dispose();
  expect(meshes.every((mesh) => mesh.material === material)).toBe(true);
});

test("reports mismatched diagnostics instead of highlighting an unrelated part", () => {
  const { model } = createModel();
  expect(() =>
    matchDiagnosticPlacements(model, {
      ...diagnostics,
      placements: [{ ...diagnostics.placements[0], position: [999, 0, 0] }],
    }),
  ).toThrow(/floating/);
});

test("all shipped diagnostic files match their original LDraw and every rendered placement", async () => {
  const directory = "static/models/spaceship-309/";
  const source = JSON.parse(await readFile(`${directory}source.json`, "utf8"));
  for (const model of Object.values(source.models) as {
    local_ldraw_file: string;
    local_packed_file: string;
    local_diagnostics_file: string;
  }[]) {
    const data = JSON.parse(await readFile(directory + model.local_diagnostics_file, "utf8"));
    const ldraw = await readFile(directory + model.local_ldraw_file);
    expect(createHash("sha256").update(ldraw).digest("hex")).toBe(data.modelSha256);
    const loader = new LDrawLoader();
    loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
    const group = await parsePackedModel(
      loader,
      await readFile(directory + model.local_packed_file, "utf8"),
    );
    const placements = matchDiagnosticPlacements(group, data);
    expect(placements.size).toBe(data.placements.length);
  }
}, 60_000);
