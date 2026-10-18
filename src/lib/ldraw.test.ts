import { readFile } from "node:fs/promises";
import { expect, test } from "vitest";
import { Vector3, type Group, type Object3D } from "three";
import { LDrawLoader } from "three/examples/jsm/loaders/LDrawLoader.js";
import { LDrawConditionalLineMaterial } from "three/addons/materials/LDrawConditionalLineMaterial.js";
import { createPartWarmup, parsePackedModel } from "./ldraw";

function createLoader() {
  const loader = new LDrawLoader();
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  return loader;
}

test.each(["", "0 FILE main.ldr\n"])(
  "preserves repeated part placements, transforms, and colors with root header %j",
  async (header) => {
    const model = await parsePackedModel(
      createLoader(),
      `${header}0 !LDRAW_ORG Model
0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333
0 !COLOUR Blue CODE 1 VALUE #0000FF EDGE #333333
1 4 10 0 0 1 0 0 0 1 0 0 0 1 brick.dat
1 1 30 0 0 1 0 0 0 1 0 0 0 1 brick.dat
0 FILE brick.dat
0 !LDRAW_ORG Part
3 16 0 0 0 10 0 0 0 10 0
`,
    );

    expect(model.children).toHaveLength(2);
    expect(model.children.map((placement) => placement.position.x)).toEqual([10, 30]);
    expect(model.children.map((placement) => placement.userData.colorCode)).toEqual(["4", "1"]);
    expect(model.children.map((placement) => placement.children[0])).toMatchObject([
      { material: { color: { r: 1, g: 0, b: 0 } } },
      { material: { color: { r: 0, g: 0, b: 1 } } },
    ]);
  },
);

const NESTED_MODEL = `0 FILE main.ldr
0 !LDRAW_ORG Model
0 !COLOUR Red CODE 4 VALUE #FF0000 EDGE #333333
0 !COLOUR Blue CODE 1 VALUE #0000FF EDGE #333333
1 4 10 0 0 1 0 0 0 1 0 0 0 1 tower-a.ldr
1 1 50 0 0 1 0 0 0 1 0 0 0 1 tower-b.ldr
1 1 100 0 0 1 0 0 0 1 0 0 0 1 tower-a.ldr
0 FILE tower-a.ldr
0 !LDRAW_ORG Model
1 16 1 0 0 1 0 0 0 1 0 0 0 1 brick.dat
1 16 2 0 0 1 0 0 0 1 0 0 0 1 BRICK.DAT
1 16 3 0 0 1 0 0 0 1 0 0 0 1 assembly.dat
0 FILE tower-b.ldr
0 !LDRAW_ORG Model
1 16 4 0 0 1 0 0 0 1 0 0 0 1 tower-a.ldr
1 16 5 0 0 1 0 0 0 1 0 0 0 1 brick.dat
0 FILE assembly.dat
0 !LDRAW_ORG Shortcut
1 16 0 0 0 1 0 0 0 1 0 0 0 1 detail.dat
0 FILE brick.dat
0 !LDRAW_ORG Part
1 16 0 0 0 1 0 0 0 1 0 0 0 1 body.dat
0 FILE body.dat
0 !LDRAW_ORG Subpart
1 16 0 0 0 1 0 0 0 1 0 0 0 1 triangle.dat
0 FILE triangle.dat
0 !LDRAW_ORG Primitive
3 16 0 0 0 10 0 0 0 10 0
0 FILE detail.dat
0 !LDRAW_ORG Unofficial_Part
3 16 0 0 0 5 0 0 0 5 0
0 FILE unused.dat
0 !LDRAW_ORG Part
3 16 0 0 0 1 0 0 0 1 0
`;

test("warm-up contains one instance of each part reachable through nested submodels", async () => {
  const warmupText = createPartWarmup(NESTED_MODEL)!;
  const warmup = await new Promise<Group>((resolve, reject) =>
    createLoader().parse(warmupText, resolve, reject),
  );
  expect(warmup.children.map(({ name }) => name).sort()).toEqual(["brick.dat", "detail.dat"]);
  expect(warmup.children.map(({ userData }) => userData.type).sort()).toEqual([
    "Part",
    "Unofficial_Part",
  ]);
});

test("preserves nested submodel placements, transforms, and colors", async () => {
  const model = await parsePackedModel(createLoader(), NESTED_MODEL);
  expect(model.children.map(({ name }) => name)).toEqual([
    "tower-a.ldr",
    "tower-b.ldr",
    "tower-a.ldr",
  ]);
  const partPlacements: Object3D[] = [];
  model.traverse((object) => {
    if (["Part", "Unofficial_Part"].includes(object.userData.type)) partPlacements.push(object);
  });
  expect(partPlacements.map((part) => part.getWorldPosition(new Vector3()).x)).toEqual([
    11, 12, 13, 55, 56, 57, 55, 101, 102, 103,
  ]);
  expect(partPlacements[0].children[0]).toMatchObject({
    material: { color: { r: 1, g: 0, b: 0 } },
  });
  expect(partPlacements[3].children[0]).toMatchObject({
    material: { color: { r: 0, g: 0, b: 1 } },
  });
});

test("loads the full Victoria Harbour model with its tower submodels", async () => {
  const text = await readFile("static/models/teaser/victoria-harbour.packed.mpd", "utf8");
  const model = await parsePackedModel(createLoader(), text);

  // Root placements include individual parts and entire tower submodels.
  expect(model.children).toHaveLength(1597);
  expect(model.children.filter((placement) => placement.name === "parts/91405.dat")).toHaveLength(
    198,
  );
  expect(
    model.children.find((placement) => placement.name === "tower_ifc.ldr")?.children.length,
  ).toBeGreaterThan(1);
}, 60_000);
