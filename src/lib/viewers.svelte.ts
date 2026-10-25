import { SvelteSet } from "svelte/reactivity";
import type { DiagnosticDisplay } from "./model-diagnostics";
import type { ModelView } from "./models";

export interface Viewer extends DiagnosticDisplay {
  readonly model: ModelView;
  /** The element the viewer's model is drawn over. */
  readonly window?: HTMLElement;
  /** Records that the model loaded with this many build steps. */
  loaded(steps: number): void;
  /** Records that the model failed to load or draw. */
  failed(): void;
}

export interface CanvasState {
  /** Rebuilds the canvas; present while it has failed to start. */
  retry?: () => void;
}

/** Mounted viewers, which the page's shared canvas draws once their models start loading. */
export const viewers = new SvelteSet<Viewer>();

/** The page's shared canvas for inline viewers. */
export const inlineCanvas = $state<CanvasState>({});

/** The open expanded dialog, which the page's expanded canvas moves into. */
export const expandedView = $state<CanvasState & { viewer?: Viewer; window?: HTMLElement }>({});
