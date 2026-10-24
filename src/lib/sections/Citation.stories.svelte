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
    const copyButton = canvas.getByRole("button", { name: "Copy" });
    await step("Section has the expected elements", async () => {
      await expect(canvas.getByRole("heading", { level: 2 })).toBeVisible();
      await expect(canvas.queryAllByRole("paragraph")[0]).toBeVisible();
      await expect(copyButton).toBeVisible();
    });
    await step("Copying puts the citation on the clipboard", async () => {
      const citation = canvas.getByTestId("citation").textContent;
      await userEvent.click(copyButton);
      await waitFor(() => expect(copyButton).toHaveTextContent("Copied!"));
      await expect(navigator.clipboard.readText()).resolves.toBe(citation);
      await waitFor(() => expect(copyButton).toHaveTextContent("Copy"), { timeout: 5_000 });
    });
  }}
/>
