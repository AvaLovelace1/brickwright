import { Box3, Vector3, type Group, type Object3D } from "three";
import { LDrawLoader } from "three/addons/loaders/LDrawLoader.js";
import { LDrawConditionalLineMaterial } from "three/addons/materials/LDrawConditionalLineMaterial.js";
import { cached } from "./cached";

export function createLoader({ smoothNormals = true } = {}) {
  const loader = new LDrawLoader();
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  loader.smoothNormals = smoothNormals;
  return loader;
}

const loader = createLoader();
let queue: Promise<unknown> = Promise.resolve();
// A message task yields like setTimeout(0), without timer throttling or fake timers delaying it.
const yieldToBrowser = () =>
  new Promise<void>((resolve) => {
    const { port1, port2 } = new MessageChannel();
    port1.onmessage = () => {
      port1.close();
      resolve();
    };
    port2.postMessage(null);
  });

const loadCenteredModel = cached((url) => {
  const model = queue.then(async () => {
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Unable to load model: ${response.status} ${url}`);
    const group = await parsePackedModel(loader, await response.text());
    group.rotation.x = Math.PI;
    const box = new Box3().setFromObject(group);
    const scale = 2 / Math.max(...box.getSize(new Vector3()).toArray());
    group.scale.setScalar(scale);
    group.position.copy(box.getCenter(new Vector3())).multiplyScalar(-scale);
    return group;
  });
  // Serialize parsing and let the browser handle input between models.
  queue = model.then(yieldToBrowser, yieldToBrowser);
  return model;
});

export async function loadModel(url: string): Promise<Group> {
  return (await loadCenteredModel(url)).clone();
}

function referencedFilenames(text: string): string[] {
  return text.split("\n").flatMap((line) => {
    const tokens = line.trim().split(/\s+/);
    // A type-1 reference starts with its color, position, and transform matrix.
    return tokens[0] === "1"
      ? [tokens.slice(14).join(" ").replaceAll("\\", "/").toLowerCase()]
      : [];
  });
}

/** One placement per reachable part, including parts used by nested assemblies. */
export function createPartWarmup(text: string): string | undefined {
  // The first block is the root, with or without its optional initial FILE header.
  const [root, ...definitionTexts] = text.split(/(?=^0 FILE )/m);
  const definitions = new Map<string, string>();
  for (const definition of definitionTexts) {
    const filename = definition.split("\n", 1)[0].slice("0 FILE ".length).trim().toLowerCase();
    definitions.set(filename, definition);
  }

  const visitedFilenames = new Set<string>();
  const partFilenames: string[] = [];
  function collectParts(filename: string) {
    if (visitedFilenames.has(filename)) return;
    visitedFilenames.add(filename);
    const definition = definitions.get(filename);
    if (!definition) return;
    // These are the two types whose geometry LDrawLoader caches.
    if (/^0 !LDRAW_ORG (?:Unofficial_)?Part\b/m.test(definition)) partFilenames.push(filename);
    for (const referencedFilename of referencedFilenames(definition))
      collectParts(referencedFilename);
  }
  for (const filename of referencedFilenames(root)) collectParts(filename);

  if (!partFilenames.length) return undefined;
  const colors = root.split("\n").filter((line) => line.trim().startsWith("0 !COLOUR "));
  return [
    "0 !LDRAW_ORG Model",
    ...colors,
    ...partFilenames.map((filename) => `1 16 0 0 0 1 0 0 0 1 0 0 0 1 ${filename}`),
    ...definitionTexts,
  ].join("\n");
}

/**
 * Prime the cache before assembling repeated placements: LDrawLoader can start
 * duplicate geometry builds when references to an uncached part load concurrently.
 */
export async function parsePackedModel(loader: LDrawLoader, text: string): Promise<Group> {
  const parse = (source: string) =>
    new Promise<Group>((resolve, reject) => loader.parse(source, resolve, reject));
  const warmupText = createPartWarmup(text);
  if (warmupText) await parse(warmupText);
  return parse(text);
}

/** Every part in file order, including parts nested in submodels. */
export function listParts(object: Object3D): Object3D[] {
  if (/Part|Shortcut/.test(object.userData.type ?? "")) return [object];
  return object.children.flatMap(listParts);
}
