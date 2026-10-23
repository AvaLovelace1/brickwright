import { on } from "svelte/events";
import { createSubscriber } from "svelte/reactivity";

const subscribe = createSubscriber((update) => on(document, "visibilitychange", update));

export function isPageVisible() {
  subscribe();
  return !document.hidden;
}
