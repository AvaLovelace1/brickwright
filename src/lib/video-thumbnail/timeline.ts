import { cubicOut } from "svelte/easing";
import { FEASIBILITY_CHECKS } from "../viewer/model-diagnostics";
import { SUBTITLE } from "../paper";

/**
 * `*Asterisks*` italicize part of a prompt. `angle` is where the camera starts orbiting, in degrees;
 * 45 is the site's default view.
 */
export const SCENES = [
  {
    prompt: "a lighthouse besieged by a sea serpent",
    model: "teaser/lighthouse-sea-serpent",
    angle: -45,
  },
  // A relief: the orbit sweeps past its front.
  { prompt: "Van Gogh’s *The Starry Night*", model: "teaser/starry-night", angle: 120 },
  { prompt: "a poseable crab", model: "teaser/poseable-crab", angle: -45 },
] as const;

export const FPS = 30;

// Seconds. The video opens on the finished title, so it loops seamlessly and Hugging Face's paused
// first frame shows the title.
const SLIDE = 0.5;
const LEAVE = 0.5;
const USER_AT = 0.6;
const ROBOT_AT = 1.2;
const BUILD = 6;
const HOLD = 2.5;
const CARDS_DELAY = 0.3;
const CARD_STAGGER = 0.3;
const OUTRO_STAGGER = 0.15;
const TITLE_DELAY = 0.2;
const TYPING_DELAY = 0.4;
const TYPING_SPEED = 30; // Characters per second.
const CARET_BLINK = 0.5;
const CARET_LINGER = 3 * CARET_BLINK;
const TITLE_HOLD = 2;

const SLIDE_DISTANCE = 12; // CSS pixels.
const ORBIT_SPEED = 12; // Degrees per second.

/** Each scene's prompt and model appear at `start`; the previous prompt leaves just before. */
const sceneTimes: { start: number; buildStart: number; buildEnd: number }[] = [];
for (const index of SCENES.keys()) {
  const start = index === 0 ? ROBOT_AT : sceneTimes[index - 1].buildEnd + HOLD + LEAVE;
  const buildStart = index === 0 ? start : start + SLIDE;
  sceneTimes.push({ start, buildStart, buildEnd: buildStart + BUILD });
}
const CARDS_AT = sceneTimes[0].buildEnd + CARDS_DELAY;
const OUTRO_AT = sceneTimes.at(-1)!.buildEnd + HOLD;
const TITLE_AT = OUTRO_AT + OUTRO_STAGGER + LEAVE + TITLE_DELAY;
const TYPING_AT = TITLE_AT + TYPING_DELAY;
const TYPED_AT = TYPING_AT + SUBTITLE.length / TYPING_SPEED;

export const DURATION = TYPED_AT + TITLE_HOLD;

const progress = (t: number, start: number, duration: number) =>
  Math.min(Math.max((t - start) / duration, 0), 1);

/**
 * Appears at `start`, then slides up into place, optionally fading in. After `end`, it keeps
 * sliding up as it fades out.
 */
function appearance(t: number, start: number, end = Infinity, { fade = false } = {}) {
  if (t >= end) {
    const out = cubicOut(progress(t, end, LEAVE));
    return { visible: out < 1, offset: -SLIDE_DISTANCE * out, opacity: 1 - out };
  }
  const slide = cubicOut(progress(t, start, SLIDE));
  return { visible: t >= start, offset: SLIDE_DISTANCE * (1 - slide), opacity: fade ? slide : 1 };
}

export type Appearance = ReturnType<typeof appearance>;

/** Everything shown `t` seconds into the video. */
export function frameAt(t: number) {
  const scene = Math.max(
    sceneTimes.findLastIndex(({ start }) => t >= start),
    0,
  );
  const { start, buildStart } = sceneTimes[scene];
  const nextStart = sceneTimes[scene + 1]?.start ?? Infinity;
  // The title enters at the end of the video and leaves at the start of the next loop.
  const titleTime = t < TITLE_AT ? t + DURATION : t;
  return {
    user: appearance(t, USER_AT, OUTRO_AT),
    robot: appearance(t, ROBOT_AT, OUTRO_AT + OUTRO_STAGGER),
    cards: FEASIBILITY_CHECKS.map((text, i) => ({
      text,
      ...appearance(t, CARDS_AT + i * CARD_STAGGER),
    })),
    scene,
    prompt: {
      text: SCENES[scene].prompt,
      // The first prompt arrives with its speech bubble.
      ...appearance(t, scene === 0 ? -Infinity : start, nextStart - LEAVE),
    },
    build: progress(t, buildStart, BUILD),
    cameraAngle: SCENES[scene].angle + ORBIT_SPEED * (t - start),
    title: {
      ...appearance(titleTime, TITLE_AT, DURATION, { fade: true }),
      typed: Math.floor(progress(titleTime, TYPING_AT, TYPED_AT - TYPING_AT) * SUBTITLE.length),
      caret:
        titleTime < TYPED_AT ||
        (titleTime < TYPED_AT + CARET_LINGER &&
          Math.floor((titleTime - TYPED_AT) / CARET_BLINK) % 2 === 0),
    },
  };
}
export type Frame = ReturnType<typeof frameAt>;
