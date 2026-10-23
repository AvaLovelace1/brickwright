import { prefersReducedMotion } from "svelte/motion";

export function readSetting(key: string): string | null {
  try {
    return localStorage.getItem(key);
  } catch {
    return null;
  }
}

export function saveSetting(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    // Keep the in-memory setting.
  }
}

const ROTATION_KEY = "brickwright-rotation";
const savedRotation = readSetting(ROTATION_KEY);
let rotationPreference = $state(
  savedRotation === "true" ? true : savedRotation === "false" ? false : undefined,
);

export const viewerSettings = {
  get rotateModels() {
    return rotationPreference ?? !prefersReducedMotion.current;
  },
  set rotateModels(enabled: boolean) {
    rotationPreference = enabled;
    saveSetting(ROTATION_KEY, String(enabled));
  },
};
