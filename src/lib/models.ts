import type { ModelDiagnostics } from "./model-diagnostics";
import { isPageVisible } from "./page-visibility.svelte";

export interface ModelView {
  ldr: string;
  ldrPacked: string;
  caption: string;
  stepsShown: number;
  maxSteps: number;
  window?: HTMLElement;
  status: "idle" | "loading" | "loaded" | "error";
  inViewport: boolean;
  expanded: boolean;
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

export function modelFiles(name: string): Pick<ModelView, "ldr" | "ldrPacked" | "diagnosticsUrl"> {
  const path = `./assets/models/${name}`;
  return {
    ldr: urls[`${path}.ldr`],
    ldrPacked: urls[`${path}.packed.mpd`],
    diagnosticsUrl: urls[`${path}.diagnostics.json`],
  };
}

export function createModel(name: string, caption: string): ModelView {
  return {
    ...modelFiles(name),
    caption,
    stepsShown: 1,
    maxSteps: 1,
    status: "idle",
    inViewport: false,
    expanded: false,
  };
}

/** Which of the model's views animates, if the page is visible and the view is on screen. */
export function activeView(model: ModelView): "inline" | "expanded" | undefined {
  if (!isPageVisible()) return undefined;
  if (model.expanded) return "expanded";
  return model.inViewport ? "inline" : undefined;
}
