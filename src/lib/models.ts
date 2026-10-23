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
  loadError?: boolean;
  loadAttempt?: number;
  activeView?: "inline" | "expanded";
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
  return {
    ldr: urls[`${path}.ldr`],
    ldrPacked: urls[`${path}.packed.mpd`],
    diagnosticsUrl: urls[`${path}.diagnostics.json`],
    caption,
    stepsShown: 1,
    maxSteps: 1,
  };
}
