import type { ModelDiagnostics } from "./model-diagnostics";

export interface ModelView {
  ldr: string;
  ldrPacked: string;
  caption: string;
  stepsShown: number;
  maxSteps: number;
  window?: HTMLElement;
  loaded?: boolean;
  loadRequested?: boolean;
  diagnosticsUrl?: string;
  diagnostics?: ModelDiagnostics;
  diagnosticsError?: boolean;
}

// Import URLs only; viewers fetch geometry and diagnostics when they become visible.
const urls = import.meta.glob<string>(
  [
    "./assets/models/**/*.ldr",
    "./assets/models/**/*.packed.mpd",
    "./assets/models/**/*.diagnostics.json",
  ],
  { eager: true, query: "?url&no-inline", import: "default" },
);

export function createModel(name: string, caption: string): ModelView {
  const path = `./assets/models/${name}`;
  const ldr = urls[`${path}.ldr`];
  const ldrPacked = urls[`${path}.packed.mpd`];
  if (!ldr || !ldrPacked) throw new Error(`Missing model assets: ${name}`);
  return {
    ldr,
    ldrPacked,
    diagnosticsUrl: urls[`${path}.diagnostics.json`],
    caption,
    stepsShown: 1,
    maxSteps: 1,
  };
}
