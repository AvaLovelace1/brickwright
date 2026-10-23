import { afterEach, expect, test, vi } from "vitest";
import { readSetting, saveSetting } from "./settings.svelte";

afterEach(() => {
  vi.unstubAllGlobals();
});

test("saved settings can be read back", () => {
  const values = new Map<string, string>();
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
  });
  saveSetting("brickwright-test", "on");
  expect(readSetting("brickwright-test")).toBe("on");
});

test("settings tolerate unavailable browser storage", () => {
  const unavailable = () => {
    throw new DOMException("Storage is disabled", "SecurityError");
  };
  vi.stubGlobal("localStorage", { getItem: unavailable, setItem: unavailable });
  expect(() => saveSetting("brickwright-test", "on")).not.toThrow();
  expect(readSetting("brickwright-test")).toBeNull();
});

test("rotation follows the saved preference as soon as settings load", async () => {
  vi.stubGlobal("localStorage", { getItem: () => "false", setItem: () => {} });
  vi.resetModules();
  const { viewerSettings } = await import("./settings.svelte");
  expect(viewerSettings.rotateModels).toBe(false);
});
