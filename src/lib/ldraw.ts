import type { Group } from "three";
import type { LDrawLoader } from "three/examples/jsm/loaders/LDrawLoader.js";

function referencedFilenames(text: string): string[] {
  return text.split("\n").flatMap((line) => {
    const tokens = line.trim().split(/\s+/);
    // A type-1 reference starts with its color, position, and transform matrix.
    return tokens[0] === "1"
      ? [tokens.slice(14).join(" ").replaceAll("\\", "/").toLowerCase()]
      : [];
  });
}

/**
 * Create a flat warm-up model with one placement of each reachable part.
 * Follow submodels and geometry dependencies, using LDraw metadata to distinguish
 * cacheable parts from assemblies, subparts, and primitives.
 */
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
  // The root places parts only; embedded definitions supply their geometry dependencies.
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
