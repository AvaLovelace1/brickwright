<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, waitFor, within } from "storybook/test";
  import { systemMessage, type DemoStep } from "#lib/content/method.js";
  import MethodChat from "./MethodChat.svelte";

  const { Story } = defineMeta({
    title: "Content/MethodChat",
    component: MethodChat,
    tags: ["autodocs"],
  });

  const messages: DemoStep[] = [
    {
      stage: "input",
      title: "Build request",
      role: "User",
      revision: null,
      text: "Build a red\nhouse.\n\nKeep it to `20` parts.",
    },
    {
      stage: "explore",
      title: "Choose parts",
      role: "Agent",
      revision: null,
      text: "I’ll inspect the `slope` parts.\r\n \t\r\nThen I’ll use `search_parts` to choose a roof.\r\n\r\n\r\n",
      call: "explore('search_parts(\"slope\")')",
      result: { kind: "text", text: "3038.dat Slope Brick 45 2 x 3" },
    },
  ];
</script>

<Story
  name="Multiple Paragraphs"
  args={{ messages, playing: false }}
  play={async ({ canvas }) => {
    const [system, user, agent] = within(canvas.getByRole("log")).getAllByRole("listitem");
    await expect(system.innerText.replace(/\s+/g, " ")).toContain(
      systemMessage.text.replaceAll("`", "").replace(/\s+/g, " ").trim(),
    );
    await expect(within(system).getByText("(paraphrased)", { exact: true })).toBeInTheDocument();

    const userParagraphs = within(user).getAllByRole("paragraph");
    await expect(userParagraphs).toHaveLength(2);
    await expect(userParagraphs[0]).toHaveTextContent("Build a red house.");
    await expect(userParagraphs[1]).toHaveTextContent("Keep it to 20 parts.");
    await expect(
      within(userParagraphs[1]).getByText("20", { selector: "code" }),
    ).toBeInTheDocument();

    // Two message paragraphs, followed by the tool result; no empty trailing paragraphs.
    const agentParagraphs = within(agent).getAllByRole("paragraph");
    await expect(agentParagraphs).toHaveLength(3);
    await expect(agentParagraphs[0]).toHaveTextContent("I’ll inspect the slope parts.");
    await expect(agentParagraphs[1]).toHaveTextContent(
      "Then I’ll use search_parts to choose a roof.",
    );
    await expect(
      within(agentParagraphs[1]).getByText("search_parts", { selector: "code" }),
    ).toBeInTheDocument();
    await expect([...agent.querySelectorAll("code")].at(-1)).toHaveTextContent(messages[1].call!);
    await expect(within(agent).getByRole("group", { name: "Tool result" })).toHaveTextContent(
      "3038.dat Slope Brick 45 2 x 3",
    );
  }}
/>

<Story
  name="Thinking"
  args={{ messages: [], playing: true }}
  play={async ({ canvas, canvasElement }) => {
    await expect(canvas.getByText(/^Agent is thinking/)).toBeVisible();
    const bounceAnimations = () =>
      canvasElement
        .getAnimations({ subtree: true })
        .filter(
          (animation) => animation instanceof CSSAnimation && animation.animationName === "bounce",
        );

    if (matchMedia("(prefers-reduced-motion: reduce)").matches) {
      await expect(bounceAnimations()).toHaveLength(0);
      return;
    }

    await waitFor(() => {
      const animations = bounceAnimations();
      expect(animations).toHaveLength(3);
      expect(animations.map((animation) => animation.effect?.getTiming().delay)).toEqual([
        0, 150, 300,
      ]);
    });
  }}
/>
