import { cached } from "./cached";

interface DiagnosticPlacement {
  id: string;
  part: string;
  position: number[];
  rotation: number[];
}

export interface ModelDiagnostics {
  placements: DiagnosticPlacement[];
  floating: string[];
  collisions: [string, string][];
  intersectionPositions: Float32Array;
}

export const FEASIBILITY_CHECKS = [
  "Real LEGO® parts",
  "No collisions or floaters",
  "Fully connected",
];

/** Separate grounded assemblies can be valid; connectivity is a separate property. */
export function isPhysicallyValid(
  data: Pick<ModelDiagnostics, "collisions" | "floating">,
): boolean {
  return data.collisions.length === 0 && data.floating.length === 0;
}

export const loadDiagnostics = cached(async (url): Promise<ModelDiagnostics> => {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Unable to load diagnostics: ${response.status}`);
  const data = await response.json();
  // A typed array keeps Svelte from proxying every coordinate when the model enters $state.
  return { ...data, intersectionPositions: new Float32Array(data.intersectionPositions) };
});

export interface DiagnosticDisplay {
  highlightCollisions: boolean;
  showIntersections: boolean;
}
