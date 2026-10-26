import { describe, expect, test } from "vitest";
import { SUBTITLE } from "../paper";
import { DURATION, FPS, SCENES, frameAt } from "./timeline";

const times = Array.from({ length: Math.ceil(DURATION * FPS) + 1 }, (_, i) => i / FPS);
const frames = times.map((t) => ({ t, ...frameAt(t) }));
const isSorted = (values: number[]) =>
  values.every((value, i) => i === 0 || values[i - 1] <= value);

describe("frameAt", () => {
  const userShown = frames.find((frame) => frame.user.visible)!;

  test("opens on the full title, which leaves before the user prompt appears", () => {
    expect(frameAt(0).title).toMatchObject({ visible: true, opacity: 1, typed: SUBTITLE.length });
    expect(userShown.title.visible).toBe(false);
    expect(userShown.robot.visible).toBe(false);
    expect(userShown.scene).toBe(0);
  });

  test("loops seamlessly by ending on the opening frame", () => {
    const last = frameAt(DURATION);
    expect(last.title).toEqual(frameAt(0).title);
    expect(last.user.visible || last.robot.visible).toBe(false);
  });

  test("builds each scene's model while orbiting it from that scene's starting view", () => {
    const order = frames.filter((frame) => frame.robot.visible).map((frame) => frame.scene);
    expect(order.filter((scene, i) => scene !== order[i - 1])).toEqual([...SCENES.keys()]);
    for (const [index, scene] of SCENES.entries()) {
      const shown = frames.filter((frame) => frame.robot.visible && frame.scene === index);
      const build = shown.map((frame) => frame.build);
      expect([build[0], build.at(-1)]).toEqual([0, 1]);
      expect(isSorted(build)).toBe(true);
      const angles = shown.map((frame) => frame.cameraAngle);
      expect(angles[0]).toBeCloseTo(scene.angle, 0);
      expect(angles.at(-1)).toBeGreaterThan(angles[0]);
      expect(isSorted(angles)).toBe(true);
    }
  });

  test("reveals the feasibility cards one at a time after the first build and keeps them", () => {
    const firstBuilt = frames.find((frame) => frame.build === 1)!;
    expect(firstBuilt.cards.some((card) => card.visible)).toBe(false);
    const shownAt = firstBuilt.cards.map(
      (_, i) => frames.find((frame) => frame.cards[i].visible)!.t,
    );
    expect(isSorted(shownAt)).toBe(true);
    expect(new Set(shownAt).size).toBe(shownAt.length);
    const afterAll = frames.filter((frame) => frame.t >= shownAt.at(-1)!);
    expect(afterAll.every((frame) => frame.cards.every((card) => card.visible))).toBe(true);
  });

  test("finishes the last model, then clears the chat before typing the title", () => {
    const leaving = frames.find((frame) => frame.scene > 0 && !frame.user.visible)!;
    expect(leaving.scene).toBe(SCENES.length - 1);
    expect(leaving.build).toBe(1);
    const titled = frames.filter((frame) => frame.t > leaving.t && frame.title.visible);
    expect(titled.every((frame) => !frame.robot.visible)).toBe(true);
    const typed = titled.map((frame) => frame.title.typed);
    expect([typed[0], typed.at(-1)]).toEqual([0, SUBTITLE.length]);
    expect(isSorted(typed)).toBe(true);
  });

  test("keeps the caret blinking briefly after typing, then hides it", () => {
    const titled = frames.filter((frame) => frame.t > userShown.t && frame.title.visible);
    const typing = titled.filter((frame) => frame.title.typed < SUBTITLE.length);
    expect(typing.every((frame) => frame.title.caret)).toBe(true);
    const caret = titled.slice(typing.length).map((frame) => frame.title.caret);
    expect(caret[0]).toBe(true);
    expect(caret.filter((shown, i) => shown && !caret[i - 1]).length).toBeGreaterThan(1);
    expect(caret.at(-1)).toBe(false);
  });
});
