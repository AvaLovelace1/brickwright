import { fade as svelteFade, fly as svelteFly, scale as svelteScale } from "svelte/transition";
import { prefersReducedMotion } from "svelte/motion";
import { cubicOut } from "svelte/easing";

const durations = { short: 150, medium: 300 };
type Duration = keyof typeof durations;

const timing = (duration: Duration) => ({ duration: durations[duration], easing: cubicOut });

export function fade(node: Element, { duration }: { duration: Duration }) {
  return svelteFade(node, timing(duration));
}

export function scale(node: Element, { duration }: { duration: Duration }) {
  return svelteScale(node, { start: prefersReducedMotion.current ? 1 : 0.8, ...timing(duration) });
}

export function fly(
  node: Element,
  { x = 0, y = 0, duration }: { x?: number; y?: number; duration: Duration },
) {
  const still = prefersReducedMotion.current;
  return svelteFly(node, { x: still ? 0 : x, y: still ? 0 : y, ...timing(duration) });
}
