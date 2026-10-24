<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Citation from "./Citation.svelte";
  import { expect, waitFor } from "storybook/test";

  const { Story } = defineMeta({
    title: "Sections/Citation",
    component: Citation,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step, userEvent }) => {
    await step("Section has the expected elements", async () => {
      const heading = canvas.getByRole("heading", { level: 2 });
      await expect(heading).toBeVisible();
      const paragraph = canvas.queryAllByRole("paragraph")[0];
      await expect(paragraph).toBeVisible();
      const copyButton = canvas.getByRole("button", { name: /copy/i });
      await expect(copyButton).toBeVisible();
    });
    await step("Copying puts the citation on the clipboard", async () => {
      const citation = canvas.getByTestId("citation").textContent;
      const copyButton = canvas.getByRole("button", { name: "Copy" });
      await userEvent.click(copyButton);
      await waitFor(() => expect(copyButton).toHaveTextContent("Copied!"));
      await expect(navigator.clipboard.readText()).resolves.toBe(citation);
      await waitFor(() => expect(copyButton).toHaveTextContent("Copy"), { timeout: 5_000 });
    });
  }}
/>
