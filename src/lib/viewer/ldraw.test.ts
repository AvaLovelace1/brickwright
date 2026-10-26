import { readFile } from "node:fs/promises";
import { expect, test, vi } from "vitest";
import { Box3, Mesh, Vector3, type Group, type Object3D } from "three";
import {
  buildSteps,
  createLoader,
  createPartWarmup,
  listParts,
  loadModel,
  parsePackedModel,
} from "./ldraw";

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

test("loads normalized clones with shared geometry and independent placement visibility", async () => {
  const url = `data:text/plain,${encodeURIComponent(NESTED_MODEL)}`;
  const [first, second] = await Promise.all([loadModel(url), loadModel(url)]);
  const bounds = new Box3().setFromObject(first);
  expect(bounds.getCenter(new Vector3()).length()).toBeLessThan(1e-6);
  expect(Math.max(...bounds.getSize(new Vector3()).toArray())).toBeCloseTo(2);
  expect(first.children).toHaveLength(3);
  expect(second).not.toBe(first);
  first.children[0].visible = false;
  expect(second.children[0].visible).toBe(true);
  const meshes = (model: Object3D) => {
    const result: Mesh[] = [];
    model.traverse((object) => {
      if (object instanceof Mesh) result.push(object);
    });
    return result;
  };
  const firstMeshes = meshes(first);
  const secondMeshes = meshes(second);
  expect(firstMeshes.length).toBeGreaterThan(0);
  for (const [index, mesh] of firstMeshes.entries()) {
    expect(secondMeshes[index].geometry).toBe(mesh.geometry);
    expect(secondMeshes[index].material).toBe(mesh.material);
  }
});

test("retries a failed download without blocking subsequent models", async () => {
  const fetch = vi.spyOn(globalThis, "fetch");
  fetch.mockResolvedValueOnce(new Response(null, { status: 503 }));
  const url = `data:text/plain,${encodeURIComponent(NESTED_MODEL)}#retry`;
  try {
    await expect(loadModel(url)).rejects.toThrow("503");
    await expect(loadModel(url)).resolves.toHaveProperty("children.length", 3);
  } finally {
    fetch.mockRestore();
  }
});

test("later models load even if timers pending after an earlier load are discarded", async () => {
  const url = (name: string) => `data:text/plain,${encodeURIComponent(NESTED_MODEL)}#${name}`;
  vi.useFakeTimers({ toFake: ["setTimeout"] });
  try {
    await loadModel(url("fake-timers"));
  } finally {
    vi.useRealTimers();
  }
  await expect(loadModel(url("real-timers"))).resolves.toHaveProperty("children.length", 3);
});

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

test("lists nested part placements in file order with their transforms and colors", async () => {
  const model = await parsePackedModel(createLoader(), NESTED_MODEL);
  expect(model.children.map(({ name }) => name)).toEqual([
    "tower-a.ldr",
    "tower-b.ldr",
    "tower-a.ldr",
  ]);
  const partPlacements = listParts(model);
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

test("builds each submodel part by part where it first appears and adds later copies whole", async () => {
  const model = await parsePackedModel(createLoader(), NESTED_MODEL);
  const steps = buildSteps(model);
  expect(steps.map(({ name }) => name)).toEqual([
    "brick.dat",
    "BRICK.DAT",
    "assembly.dat",
    "tower-a.ldr",
    "brick.dat",
    "tower-a.ldr",
  ]);
  expect(steps.map((step) => step.getWorldPosition(new Vector3()).x)).toEqual([
    11, 12, 13, 54, 55, 100,
  ]);
});

const BRICK = `0 FILE brick.dat
0 !LDRAW_ORG Part
3 16 0 0 0 10 0 0 0 10 0`;

test("adds a later copy of a submodel whole, whatever case references it", async () => {
  const model = await parsePackedModel(
    createLoader(),
    `0 FILE main.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 tower.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 TOWER.LDR
0 FILE tower.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 brick.dat
1 16 0 0 0 1 0 0 0 1 0 0 0 1 brick.dat
${BRICK}`,
  );
  expect(buildSteps(model).map(({ name }) => name)).toEqual([
    "brick.dat",
    "brick.dat",
    "TOWER.LDR",
  ]);
});

test("adds a model's loose geometry as one step", async () => {
  const model = await parsePackedModel(
    createLoader(),
    `0 FILE main.ldr
1 16 0 0 0 1 0 0 0 1 0 0 0 1 brick.dat
3 16 0 0 0 10 0 0 0 10 0
${BRICK}`,
  );
  expect(buildSteps(model).map(({ type }) => type)).toEqual(["Group", "Mesh"]);
});

test("loads the full Victoria Harbour model with its tower submodels", async () => {
  const text = await readFile("src/lib/assets/models/teaser/victoria-harbour.packed.mpd", "utf8");
  const model = await parsePackedModel(createLoader({ smoothNormals: false }), text);

  // Root placements include individual parts and entire tower submodels.
  expect(model.children).toHaveLength(1597);
  expect(model.children.filter((placement) => placement.name === "parts/91405.dat")).toHaveLength(
    198,
  );
  expect(
    model.children.find((placement) => placement.name === "tower_ifc.ldr")?.children.length,
  ).toBeGreaterThan(1);
}, 60_000);
