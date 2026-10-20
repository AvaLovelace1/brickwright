<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, userEvent as storyUserEvent, waitFor, within } from "storybook/test";
  import { install } from "@sinonjs/fake-timers";
  import { tick } from "svelte";
  import { Tooltip } from "bits-ui";
  import MethodDemo from "./MethodDemo.svelte";

  const { Story } = defineMeta({
    title: "Components/MethodDemo",
    component: MethodDemo,
    tags: ["autodocs"],
    render: template,
    parameters: { layout: "fullscreen" },
  });

  function demoElements(element: HTMLElement) {
    const canvas = within(element);
    const conversation = canvas.getByRole("log", { name: "Mock agent conversation" });
    const steps = within(canvas.getByRole("group", { name: "Demo steps" }));
    return {
      canvas,
      conversation,
      progress: canvas.getByRole("status", { name: "Demo progress" }),
      button: (name: string) => canvas.getByRole("button", { name }),
      step: (number: number) => steps.getByRole("button", { name: new RegExp(`^Step ${number}:`) }),
      messages: () => within(conversation).getAllByRole("listitem"),
      activeStages: () =>
        canvas
          .getByRole("region", { name: "Build creation flowchart" })
          .querySelectorAll('[aria-current="step"]'),
      source: () => canvas.getByLabelText("Current build.py source"),
      viewer: () => canvas.getByRole("figure", { name: "Current house build" }),
    };
  }
</script>

{#snippet template()}
  <Tooltip.Provider>
    <div class="mx-auto max-w-7xl p-4 sm:p-8"><MethodDemo /></div>
  </Tooltip.Provider>
{/snippet}

<Story
  name="Revision Loops"
  play={async ({ canvasElement, userEvent, step }) => {
    const demo = demoElements(canvasElement);
    const stages = [
      "Input",
      "explore(snippet)",
      "Write build.py",
      "validate()",
      "Write build.py",
      "validate()",
      "render()",
      "Write build.py",
      "validate()",
      "render()",
      "finalize()",
    ];
    await expect(demo.button("Previous step")).toBeDisabled();
    await expect(demo.messages()[0]).toHaveTextContent("System");
    await expect(
      within(demo.messages()[0]).getByText("(paraphrased)", { exact: true }),
    ).toBeVisible();
    await expect(within(demo.messages()[1]).getByText("User", { exact: true })).toBeVisible();
    await expect(demo.canvas.getByText("No build yet", { exact: true })).toBeVisible();
    await expect(demo.canvas.getByText("No file yet", { exact: true })).toBeVisible();

    await step("Chat, build revisions, and flowchart advance together", async () => {
      for (let index = 0; index < stages.length; index += 1) {
        if (index > 0) await userEvent.click(demo.button("Next step"));
        await expect(demo.progress).toHaveTextContent(`Step ${index + 1}/11`);
        await expect(demo.activeStages()).toHaveLength(1);
        await expect(demo.activeStages()[0]).toHaveTextContent(stages[index]);
        await expect(demo.messages()).toHaveLength(index + 2);
        if (stages[index] === "Write build.py" || stages[index] === "finalize()") {
          const result = within(demo.messages().at(-1)!).getByRole("group", {
            name: "Tool result",
          });
          await expect(within(result).getByText("OK", { exact: true })).toBeVisible();
        }
        if (index > 0) {
          const call = [...demo.messages().at(-1)!.querySelectorAll("code")].at(-1);
          await expect(call).toHaveTextContent(
            /^(explore|write_build|edit_build|validate|render|finalize)\(/,
          );
        }
      }
      await expect(demo.conversation).toHaveTextContent("model compiled to out/model.ldr");
      await expect(demo.button("Next step")).toBeDisabled();
    });
    await step(
      "Previous and jumping to the first step restore the corresponding state",
      async () => {
        await userEvent.click(demo.button("Previous step"));
        await expect(demo.activeStages()[0]).toHaveTextContent("render()");
        await expect(demo.conversation).not.toHaveTextContent("model compiled to out/model.ldr");
        await userEvent.click(demo.step(1));
        await expect(demo.button("Previous step")).toBeDisabled();
        await expect(demo.progress).toHaveTextContent("Step 1/11");
      },
    );
  }}
/>

<Story
  name="Playback"
  play={async ({ canvasElement }) => {
    const demo = demoElements(canvasElement);
    const clock = install({ toFake: ["setTimeout", "clearTimeout"] });
    const user = storyUserEvent.setup({ advanceTimers: (delay) => clock.tickAsync(delay) });
    const advance = async (milliseconds: number) => {
      await clock.tickAsync(milliseconds);
      await tick();
    };
    try {
      await expect(demo.canvas.queryByText("Agent is thinking")).toBeNull();
      await user.click(demo.button("Play demo"));
      await expect(demo.canvas.getByText("Agent is thinking…", { exact: true })).toBeVisible();
      await advance(4500);
      await expect(demo.progress).toHaveTextContent("Step 2/11");
      await user.click(demo.button("Pause demo"));
      await expect(demo.canvas.queryByText("Agent is thinking…", { exact: true })).toBeNull();
      await advance(9000);
      await expect(demo.progress).toHaveTextContent("Step 2/11");
      await user.click(demo.button("Play demo"));
      await user.click(demo.button("Next step"));
      await advance(9000);
      await expect(demo.progress).toHaveTextContent("Step 3/11");
      await expect(demo.button("Play demo")).toBeVisible();
      for (let index = 3; index < 11; index += 1) await user.click(demo.button("Next step"));
      await user.click(demo.button("Replay demo"));
      await expect(demo.progress).toHaveTextContent("Step 1/11");
      for (let index = 1; index < 11; index += 1) await advance(4500);
      await expect(demo.progress).toHaveTextContent("Step 11/11");
      await expect(demo.button("Replay demo")).toBeVisible();
      await expect(demo.canvas.queryByText("Agent is thinking…", { exact: true })).toBeNull();
      await advance(9000);
      await expect(demo.progress).toHaveTextContent("Step 11/11");
    } finally {
      clock.uninstall();
    }
  }}
/>

<Story
  name="Jump and Keyboard Navigation"
  play={async ({ canvasElement }) => {
    const demo = demoElements(canvasElement);
    const clock = install({ toFake: ["setTimeout", "clearTimeout"] });
    const user = storyUserEvent.setup({ advanceTimers: (delay) => clock.tickAsync(delay) });
    try {
      await expect(
        within(demo.canvas.getByRole("group", { name: "Demo steps" })).getAllByRole("button"),
      ).toHaveLength(11);
      await user.click(demo.button("Play demo"));
      await user.click(demo.step(8));
      await expect(demo.progress).toHaveTextContent("Step 8/11");
      await expect(demo.step(8)).toHaveAttribute("aria-current", "step");
      await expect(demo.activeStages()[0]).toHaveTextContent("Write build.py");
      await expect(demo.source()).toHaveTextContent("DOOR_X = 3");
      await expect(demo.messages()).toHaveLength(9);
      await expect(demo.button("Play demo")).toBeVisible();
      await clock.tickAsync(9000);
      await tick();
      await expect(demo.progress).toHaveTextContent("Step 8/11");

      demo.step(3).focus();
      await user.keyboard("{Enter}");
      await expect(demo.step(3)).toHaveFocus();
      await expect(demo.progress).toHaveTextContent("Step 3/11");
      await expect(demo.source()).toHaveTextContent("roof_z = z + 2");
      await expect(demo.messages()).toHaveLength(4);
      await user.click(demo.step(11));
      await expect(demo.button("Replay demo")).toBeVisible();
      await expect(demo.conversation).toHaveTextContent("model compiled to out/model.ldr");
      demo.step(1).focus();
      await user.keyboard(" ");
      await expect(demo.progress).toHaveTextContent("Step 1/11");
      await expect(demo.canvas.getByText("No build yet", { exact: true })).toBeVisible();
      await expect(demo.canvas.getByText("No file yet", { exact: true })).toBeVisible();
    } finally {
      clock.uninstall();
    }
  }}
/>

<Story
  name="Build Revisions and Diagnostics"
  play={async ({ canvasElement, userEvent, step }) => {
    const demo = demoElements(canvasElement);
    await userEvent.click(demo.step(3));
    demo.viewer().scrollIntoView({ block: "center" });
    await waitFor(() => expect(demo.viewer()).toHaveAttribute("aria-busy", "false"), {
      timeout: 45_000,
    });
    await waitFor(
      () => expect(within(demo.viewer()).getByRole("status")).toHaveTextContent("Invalid"),
      { timeout: 45_000 },
    );

    await step("Displayed source matches the downloaded build.py", async () => {
      const download = demo.canvas.getByRole("link", {
        name: "Download code",
      }) as HTMLAnchorElement;
      await expect(download).toHaveAttribute("download", "build.py");
      const response = await fetch(download.href);
      await expect(response.ok).toBe(true);
      await expect(demo.source().textContent).toBe(await response.text());
    });
    await step("Diagnostic controls operate on the real model", async () => {
      await expect(demo.canvas.getAllByRole("checkbox")).toHaveLength(2);
      const intersections = demo.canvas.getByRole("checkbox", { name: "Show intersections" });
      await expect(intersections).toBeChecked();
      await expect(within(demo.viewer()).getByText("Intersections", { exact: true })).toBeVisible();
      await userEvent.click(intersections);
      await expect(intersections).not.toBeChecked();
      await expect(within(demo.viewer()).queryByText("Intersections", { exact: true })).toBeNull();
      await userEvent.click(intersections);
      await expect(within(demo.viewer()).getByText("Intersections", { exact: true })).toBeVisible();
      await userEvent.click(
        demo.canvas.getByRole("checkbox", { name: "Highlight colliding bricks" }),
      );
    });
    await step("Each revision updates the viewer, download, and displayed source", async () => {
      for (const [number, revision, source, status] of [
        [3, "draft1", "roof_z = z + 2", "Invalid"],
        [5, "draft2", "roof_z = z + 3", "Valid"],
        [8, "final", "DOOR_X = 3", "Valid"],
      ] as const) {
        await userEvent.click(demo.step(number));
        demo.viewer().scrollIntoView({ block: "center" });
        await waitFor(() => expect(demo.viewer()).toHaveAttribute("aria-busy", "false"), {
          timeout: 45_000,
        });
        await expect(
          within(demo.viewer()).getByRole("link", { name: "Download LDraw" }),
        ).toHaveAttribute("href", expect.stringContaining(`house-${revision}.ldr`));
        await waitFor(() =>
          expect(within(demo.viewer()).getByRole("status")).toHaveTextContent(status),
        );
        await expect(demo.source()).toHaveTextContent(source);
        await expect(
          demo.canvas.getByRole("checkbox", { name: "Highlight colliding bricks" }),
        ).toBeChecked();
        await expect(demo.canvas.queryByText("Diagnostics unavailable")).toBeNull();
      }
    });
  }}
/>

<Story
  name="Control Tooltips"
  play={async ({ canvasElement, userEvent }) => {
    const demo = demoElements(canvasElement);
    const play = demo.button("Play demo");
    await userEvent.hover(play);
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(screen.getByRole("tooltip")).toHaveTextContent("Play demo");
    await userEvent.unhover(play);
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());

    const firstBuild = demo.step(3);
    const stepLabel = firstBuild.getAttribute("aria-label")!;
    await userEvent.hover(firstBuild);
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(screen.getByRole("tooltip")).toHaveTextContent(stepLabel);
    await userEvent.unhover(firstBuild);
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    firstBuild.focus();
    await waitFor(() => expect(screen.getByRole("tooltip")).toBeVisible());
    await expect(screen.getByRole("tooltip")).toHaveTextContent(stepLabel);
    await expect(firstBuild).toHaveAccessibleDescription(stepLabel);
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
    await userEvent.keyboard("{Enter}");
    await expect(demo.progress).toHaveTextContent("Step 3/11");
    await expect(firstBuild).toHaveFocus();
    await waitFor(() => expect(screen.queryByRole("tooltip")).toBeNull());
  }}
/>
