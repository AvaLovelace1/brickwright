export interface DiagnosticPlacement {
  id: string;
  part: string;
  position: number[];
  rotation: number[];
}

export interface ModelDiagnostics {
  version: number;
  coordinateSystem: string;
  units: string;
  placements: DiagnosticPlacement[];
  floating: string[];
  collisions: [string, string][];
  intersectionPositions: number[];
}

/** Separate grounded assemblies can be valid; connectivity is a separate property. */
export function isPhysicallyValid(
  data: Pick<ModelDiagnostics, "collisions" | "floating">,
): boolean {
  return data.collisions.length === 0 && data.floating.length === 0;
}

const downloads = new Map<string, Promise<ModelDiagnostics>>();

export function loadDiagnostics(url: string): Promise<ModelDiagnostics> {
  let download = downloads.get(url);
  if (!download) {
    download = fetch(url)
      .then(async (response) => {
        if (!response.ok) throw new Error(`Unable to load diagnostics: ${response.status}`);
        return (await response.json()) as ModelDiagnostics;
      })
      .catch((error) => {
        downloads.delete(url);
        throw error;
      });
    downloads.set(url, download);
  }
  return download;
}

export interface DiagnosticDisplay {
  highlightCollisions: boolean;
  showIntersections: boolean;
}
