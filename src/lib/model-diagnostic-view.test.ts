import { expect, test } from "vitest";
import { BoxGeometry, Group, Mesh, MeshStandardMaterial, Vector3 } from "three";
import type { ModelDiagnostics } from "./model-diagnostics";
import { createDiagnosticView, matchDiagnosticPlacements } from "./model-diagnostic-view";

const identity = [1, 0, 0, 0, 1, 0, 0, 0, 1];
const diagnostics: ModelDiagnostics = {
  placements: [
    { id: "floating", part: "brick.dat", position: [30, 0, 0], rotation: identity },
    { id: "valid", part: "brick.dat", position: [10, 0, 0], rotation: identity },
    { id: "colliding", part: "brick.dat", position: [20, 0, 0], rotation: identity },
    { id: "colliding2", part: "brick.dat", position: [40, 0, 0], rotation: identity },
  ],
  floating: ["floating", "colliding2"],
  collisions: [["colliding", "colliding2"]],
  intersectionPositions: new Float32Array([20, 0, 0, 21, 1, 0]),
};

function createAssembly() {
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

test("matches nested part placements by part and transform", () => {
  const { model, meshes } = createAssembly();
  model.rotation.x = Math.PI;
  model.scale.setScalar(0.01);
  model.position.set(1, 2, 3);
  const parts = matchDiagnosticPlacements(model, diagnostics);
  expect(parts.get("valid")).toBe(meshes[0].parent);
  expect(parts.get("colliding")).toBe(meshes[1].parent);
  expect(parts.get("floating")).toBe(meshes[2].parent);
});

test("highlights colliding bricks while fading floating-only and valid parts", () => {
  const { model, meshes, material } = createAssembly();
  const otherViewer = model.clone();
  const view = createDiagnosticView(model, diagnostics);
  view.update({ highlightCollisions: true, showIntersections: false });
  expect(meshes[0].material.opacity).toBeLessThan(0.6);
  expect(meshes[1].material.opacity).toBe(1);
  expect(meshes[2].material.opacity).toBeLessThan(0.6);
  expect(meshes[3].material.opacity).toBe(1);
  expect(material.opacity).toBe(0.6);
  expect((otherViewer.children[0].children[0].children[0] as Mesh).material).toBe(material);
  expect(view.intersections.visible).toBe(false);

  view.update({ highlightCollisions: false, showIntersections: true });
  expect(meshes.map((mesh) => mesh.material)).toEqual([material, material, material, material]);
  expect(view.intersections.visible).toBe(true);
  view.dispose();
});

test("intersection lines use the same transform as the model without becoming build steps", () => {
  const { model } = createAssembly();
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
  const { model, meshes, material } = createAssembly();
  const view = createDiagnosticView(model, diagnostics);
  view.update({ highlightCollisions: true, showIntersections: true });
  view.dispose();
  expect(meshes.every((mesh) => mesh.material === material)).toBe(true);
});

test("throws when a diagnostic placement has no matching part", () => {
  const { model } = createAssembly();
  expect(() =>
    matchDiagnosticPlacements(model, {
      ...diagnostics,
      placements: [{ ...diagnostics.placements[0], position: [999, 0, 0] }],
    }),
  ).toThrow(/floating/);
});
