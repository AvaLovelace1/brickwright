import { fade as svelteFade, fly as svelteFly, scale as svelteScale } from "svelte/transition";
import { prefersReducedMotion } from "svelte/motion";
import { cubicOut } from "svelte/easing";

const durations = { short: 150, medium: 300, long: 450 };
type Duration = keyof typeof durations;

export function fade(node: Element, { duration }: { duration: Duration }) {
  return svelteFade(node, {
    duration: durations[duration],
    easing: cubicOut,
  });
}

export function scale(node: Element, { duration }: { duration: Duration }) {
  return svelteScale(node, {
    start: prefersReducedMotion.current ? 1 : 0.8,
    duration: durations[duration],
    easing: cubicOut,
  });
}

export function fly(
  node: Element,
  { x = 0, y = 0, duration }: { x?: number; y?: number; duration: Duration },
) {
  return svelteFly(node, {
    x: prefersReducedMotion.current ? 0 : x,
    y: prefersReducedMotion.current ? 0 : y,
    duration: durations[duration],
    easing: cubicOut,
  });
}
