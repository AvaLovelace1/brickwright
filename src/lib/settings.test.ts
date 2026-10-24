import { afterEach, expect, test, vi } from "vitest";

afterEach(() => {
  vi.unstubAllGlobals();
});

async function loadSettings(storage: Pick<Storage, "getItem" | "setItem">) {
  vi.stubGlobal("localStorage", storage);
  vi.resetModules();
  return (await import("./settings.svelte")).viewerSettings;
}

test("the rotation preference persists across page loads", async () => {
  const values = new Map<string, string>();
  const storage = {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => void values.set(key, value),
  };
  for (const enabled of [true, false]) {
    (await loadSettings(storage)).rotateModels = enabled;
    expect((await loadSettings(storage)).rotateModels).toBe(enabled);
  }
});

test("the rotation preference works when browser storage is unavailable", async () => {
  const unavailable = () => {
    throw new DOMException("Storage is disabled", "SecurityError");
  };
  const settings = await loadSettings({ getItem: unavailable, setItem: unavailable });
  settings.rotateModels = false;
  expect(settings.rotateModels).toBe(false);
});
