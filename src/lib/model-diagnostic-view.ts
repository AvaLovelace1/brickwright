import {
  BufferGeometry,
  Float32BufferAttribute,
  Group,
  LineBasicMaterial,
  LineSegments,
  Material,
  Matrix3,
  Matrix4,
  Mesh,
  Object3D,
} from "three";

import type { ModelDiagnostics, DiagnosticDisplay } from "./model-diagnostics";

const partName = (name: string) =>
  name
    .replaceAll("\\", "/")
    .toLowerCase()
    .replace(/^parts\//, "");

/** Match assessed placements in original LDraw space, including nested assemblies. */
export function matchDiagnosticPlacements(
  model: Object3D,
  data: ModelDiagnostics,
): Map<string, Object3D> {
  model.updateWorldMatrix(true, true);
  const inverse = model.matrixWorld.clone().invert();
  const candidates = new Map<string, { object: Object3D; matrix: Matrix4 }[]>();
  model.traverse((object) => {
    if (!(object instanceof Group)) return;
    const name = partName(object.name);
    const list = candidates.get(name) ?? [];
    list.push({ object, matrix: new Matrix4().multiplyMatrices(inverse, object.matrixWorld) });
    candidates.set(name, list);
  });

  const placements = new Map<string, Object3D>();
  for (const placement of data.placements) {
    const [x, y, z] = placement.position;
    // LDraw rotations are row-major; Matrix3.fromArray reads column-major.
    const rotation = new Matrix3().fromArray(placement.rotation).transpose();
    const transform = new Matrix4().setFromMatrix3(rotation).setPosition(x, y, z);
    const parts = candidates.get(partName(placement.part)) ?? [];
    const index = parts.findIndex(({ matrix }) =>
      matrix.elements.every((value, i) => Math.abs(value - transform.elements[i]) < 0.001),
    );
    if (index < 0)
      throw new Error(
        `Diagnostic placement ${placement.id} (${placement.part}) does not match the model`,
      );
    placements.set(placement.id, parts.splice(index, 1)[0].object);
  }
  return placements;
}

/** Per-view materials keep highlighting isolated from cached models and other viewers. */
export function createDiagnosticView(model: Object3D, data: ModelDiagnostics) {
  const placements = matchDiagnosticPlacements(model, data);
  const colliding = new Set(data.collisions.flat());
  const isCollidingByPart = new Map(
    [...placements].map(([id, object]) => [object, colliding.has(id)]),
  );
  const opaqueMaterials = new Map<Material, Material>();
  const translucentMaterials = new Map<Material, Material>();
  const targets: {
    object: Mesh | LineSegments;
    original: Material | Material[];
    highlighted: Material | Material[];
  }[] = [];

  function highlight(material: Material, isColliding: boolean) {
    const materials = isColliding ? opaqueMaterials : translucentMaterials;
    let variant = materials.get(material);
    if (!variant) {
      variant = material.clone();
      variant.opacity = isColliding ? 1 : 0.05;
      variant.transparent = !isColliding;
      variant.depthWrite = isColliding ? material.depthWrite : false;
      materials.set(material, variant);
    }
    return variant;
  }

  model.traverse((object) => {
    if (!(object instanceof Mesh || object instanceof LineSegments)) return;
    let part: Object3D | null = object;
    while (part && !isCollidingByPart.has(part)) part = part.parent;
    // Reports with partial coverage leave some parts unassessed; their geometry stays unchanged.
    if (!part) return;
    const isColliding = isCollidingByPart.get(part)!;
    const original = object.material;
    const highlighted = Array.isArray(original)
      ? original.map((material) => highlight(material, isColliding))
      : highlight(original, isColliding);
    targets.push({ object, original, highlighted });
  });

  const geometry = new BufferGeometry();
  geometry.setAttribute("position", new Float32BufferAttribute(data.intersectionPositions, 3));
  const material = new LineBasicMaterial({
    color: 0xff0000,
    transparent: true,
    depthTest: false,
    depthWrite: false,
    toneMapped: false,
  });
  const intersections = new LineSegments(geometry, material);
  intersections.matrix.copy(model.matrix);
  intersections.matrixAutoUpdate = false;
  intersections.matrixWorldNeedsUpdate = true;
  intersections.renderOrder = 1000;
  intersections.visible = false;

  return {
    intersections,
    update({ highlightCollisions, showIntersections }: DiagnosticDisplay) {
      for (const target of targets)
        target.object.material = highlightCollisions ? target.highlighted : target.original;
      intersections.visible = showIntersections && data.intersectionPositions.length > 0;
    },
    dispose() {
      for (const target of targets) target.object.material = target.original;
      for (const variant of opaqueMaterials.values()) variant.dispose();
      for (const variant of translucentMaterials.values()) variant.dispose();
      geometry.dispose();
      material.dispose();
    },
  };
}

export type DiagnosticView = ReturnType<typeof createDiagnosticView>;
