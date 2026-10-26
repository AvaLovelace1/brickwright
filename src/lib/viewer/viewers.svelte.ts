import { createContext } from "svelte";
import { SvelteSet } from "svelte/reactivity";
import type { DiagnosticDisplay } from "./model-diagnostics";
import type { ModelView } from "./models";

export interface Viewer extends DiagnosticDisplay {
  readonly model: ModelView;
  /** The element the viewer's model is drawn over. */
  readonly window?: HTMLElement;
  /** The element the model is drawn over in the viewer's expanded dialog, while it is open. */
  readonly expandedWindow?: HTMLElement;
  /** Records that the model loaded with this many build steps. */
  loaded(steps: number): void;
  /** Records that the model failed to load or draw. */
  failed(): void;
}

/** The mounted viewers that a page's shared canvases draw. */
export class ViewerHost {
  readonly viewers = new SvelteSet<Viewer>();
  /** Rebuilds each canvas; present while that canvas has failed to start. */
  retry = $state<{ inline?: () => void; expanded?: () => void }>({});
}

export const [getViewerHost, setViewerHost] = createContext<ViewerHost>();
