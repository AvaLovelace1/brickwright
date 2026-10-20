import draft1Source from "./assets/method/house-draft1.py?raw";
import draft2Source from "./assets/method/house-draft2.py?raw";
import finalSource from "./assets/method/house-final.py?raw";
import draft1Report from "./assets/method/house-draft1.report.json";
import draft2Report from "./assets/method/house-draft2.report.json";
import finalReport from "./assets/method/house-final.report.json";

import draft1Download from "./assets/method/house-draft1.py?url&no-inline";
import draft2Download from "./assets/method/house-draft2.py?url&no-inline";
import finalDownload from "./assets/method/house-final.py?url&no-inline";

export const methodBuilds = {
  draft1: { source: draft1Source, download: draft1Download, report: draft1Report },
  draft2: { source: draft2Source, download: draft2Download, report: draft2Report },
  final: { source: finalSource, download: finalDownload, report: finalReport },
};

export type BuildRevision = keyof typeof methodBuilds;
type RenderRevision = Exclude<BuildRevision, "draft1">;

interface ValidationCheck {
  label: string;
  passed: boolean;
}

const displayedChecks = [
  { name: "no_collisions", label: "No collisions" },
  { name: "no_floating", label: "No floating parts" },
  { name: "connected", label: "1 connected component" },
  { name: "twenty_parts", label: "20 parts" },
];

function validationChecks(revision: BuildRevision): ValidationCheck[] {
  const report = methodBuilds[revision].report;
  return [
    { label: "Compiles", passed: report.build_error === null },
    ...displayedChecks.map(({ name, label }) => {
      const check = report.checks.find((check) => check.name === name);
      if (!check) throw new Error(`Missing ${name} check in the ${revision} report`);
      return { label, passed: check.passed };
    }),
  ];
}

// Blank lines separate paragraphs; backticks mark inline code.

export type Stage = "input" | "explore" | "write" | "validate" | "render" | "finalize";
export type Flow =
  | "input-explore"
  | "explore-write"
  | "write-validate"
  | "tests-fail"
  | "tests-pass"
  | "render-revise"
  | "render-ok";
export type DemoStep = {
  stage: Stage;
  title: string;
  text: string;
  revision: BuildRevision | null;
  flow?: Flow;
} & (
  | { role: "User"; call?: never; result?: never }
  | { role: "Agent"; call: string; result: ToolResult }
);

type ToolResult =
  | { kind: "text"; text: string }
  | { kind: "success"; text: string }
  | { kind: "validation"; checks: ValidationCheck[] }
  | { kind: "render"; revision: RenderRevision };

interface SystemMessage {
  role: "System";
  annotation: string;
  text: string;
  call?: never;
  result?: never;
}

export const systemMessage: SystemMessage = {
  role: "System",
  annotation: "paraphrased",
  text:
    "Write a Python file, `build.py`, that uses BrickLayer to create a LEGO® build. " +
    "This file should contain two functions: `create_build()`, which returns a `LegoBuild`, and `run_tests()`, which runs a set of tests against the build.\n\n" +
    "You are given the tools `explore`, `validate`, `render`, and `finalize`, alongside build-file editing tools. Calling `validate` runs both your custom tests and a fixed set of feasibility checks. Edit `build.py` until all tests pass and you are happy with the render, then call `finalize`. You may run `explore` at any time to investigate the BrickLayer API.\n\n" +
    "Here is the complete BrickLayer and tool documentation: […]\n",
};

export const demoSteps: readonly DemoStep[] = [
  {
    stage: "input",
    revision: null,
    title: "Build request",
    role: "User",
    text: "Build a red house with a blue roof and a brown front door, using 20 parts.",
  },
  {
    stage: "explore",
    revision: null,
    title: "Search for parts",
    role: "Agent",
    flow: "input-explore",
    text: "I’ll use four slopes for the roof, a brown brick for the door, and one baseplate to keep the house simple. Let’s inspect the available slopes.",
    call: "explore('search_parts(\"slope\")')",
    result: {
      kind: "text",
      text: "3038.dat Slope Brick 45 2 x 3\n3039.dat Slope Brick 45 2 x 2\n…",
    },
  },
  {
    stage: "write",
    revision: "draft1",
    title: "Write first-draft build",
    role: "Agent",
    flow: "explore-write",
    text: "I’ll compose the base, walls, door, and six-piece roof, and add tests for physical validity, one connected component, and the requested colors and part count.",
    call: 'write_build("build.py", source)',
    result: { kind: "success", text: "build.py written" },
  },
  {
    stage: "validate",
    revision: "draft1",
    title: "Check first draft",
    role: "Agent",
    flow: "write-validate",
    text: "The first draft is ready. I’ll check for collisions, floating parts, and disconnected components.",
    call: "validate()",
    result: { kind: "validation", checks: validationChecks("draft1") },
  },
  {
    stage: "write",
    revision: "draft2",
    title: "Correct roof height",
    role: "Agent",
    flow: "tests-fail",
    text: "The roof intersects the walls. I placed it for two-brick-high walls, but these wall and door parts are three bricks tall. I’ll move the eaves and roof up to the correct height.",
    call: 'edit_build("roof_z = z + 2", "roof_z = z + 3")',
    result: { kind: "success", text: "build.py edited" },
  },
  {
    stage: "validate",
    revision: "draft2",
    title: "Check repaired build",
    role: "Agent",
    flow: "write-validate",
    text: "The eaves and roof now sit above the three-brick-high walls. I’ll rerun all the tests before inspecting the appearance.",
    call: "validate()",
    result: { kind: "validation", checks: validationChecks("draft2") },
  },
  {
    stage: "render",
    revision: "draft2",
    title: "Inspect first render",
    role: "Agent",
    flow: "tests-pass",
    text: "All checks pass. Let’s render the house from the front to inspect the roof and door placement.",
    call: "render()",
    result: { kind: "render", revision: "draft2" },
  },
  {
    stage: "write",
    revision: "final",
    title: "Center front door",
    role: "Agent",
    flow: "render-revise",
    text: "The render shows an off-center door. I’ll shift the door and path one stud, and move the surrounding wall columns to make the front more balanced.",
    call: 'edit_build("DOOR_X = 4", "DOOR_X = 3")',
    result: { kind: "success", text: "build.py edited" },
  },
  {
    stage: "validate",
    revision: "final",
    title: "Recheck after editing",
    role: "Agent",
    flow: "write-validate",
    text: "The front elevation has changed. I’ll rerun validation to check that the revised wall is still connected and collision-free.",
    call: "validate()",
    result: { kind: "validation", checks: validationChecks("final") },
  },
  {
    stage: "render",
    revision: "final",
    title: "Review final appearance",
    role: "Agent",
    flow: "tests-pass",
    text: "The tests still pass. I’ll render once more to check the centered door and the overall appearance.",
    call: "render()",
    result: { kind: "render", revision: "final" },
  },
  {
    stage: "finalize",
    revision: "final",
    title: "Complete build",
    role: "Agent",
    flow: "render-ok",
    text: "The house is collision-free, the door is centered, and all checks pass. The twenty-part house is ready.",
    call: "finalize()",
    result: { kind: "success", text: "model compiled to out/model.ldr" },
  },
];

const secondaryStageStyle = {
  border: "border-secondary",
  topBorder: "border-t-secondary",
  ring: "ring-secondary",
  badge: "bg-secondary text-(--bb-ink-deep)",
};

export const stageStyles: Record<Stage, typeof secondaryStageStyle> = {
  input: {
    border: "border-line",
    topBorder: "border-t-line",
    ring: "ring-line",
    badge: "bg-line text-bg",
  },
  explore: {
    border: "border-accent",
    topBorder: "border-t-accent",
    ring: "ring-accent",
    badge: "bg-accent text-(--bb-ink-deep)",
  },
  write: {
    border: "border-primary",
    topBorder: "border-t-primary",
    ring: "ring-primary",
    badge: "bg-primary text-(--bb-ink-deep)",
  },
  validate: secondaryStageStyle,
  render: secondaryStageStyle,
  finalize: {
    border: "border-success",
    topBorder: "border-t-success",
    ring: "ring-success",
    badge: "bg-success text-(--bb-ink-deep)",
  },
};
