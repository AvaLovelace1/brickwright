<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import Header from "./Header.svelte";
  import { expect, screen, within, waitFor } from "storybook/test";

  const { Story } = defineMeta({
    title: "Components/Header",
    component: Header,
    tags: ["autodocs"],
    parameters: { layout: "fullscreen" },
  });
</script>

<Story
  name="Default"
  play={async ({ canvas, step, userEvent }) => {
    await step("Header has a logo", async () => {
      const logo = canvas.getByRole("img", { name: /logo/i });
      await expect(logo).toBeVisible();
    });
    await step("Header has external button links", async () => {
      for (const name of ["Paper", "Code"]) {
        const link = canvas.getByRole("link", { name });
        await expect(link).toBeVisible();
        await expect(link).toHaveAttribute("target", "_blank");
        await expect(link).toHaveAttribute("rel", "external noopener");
      }
    });
    await step("Settings contains the theme and global rotation controls", async () => {
      const trigger = canvas.getByRole("button", { name: "Settings" });
      await userEvent.click(trigger);
      const dialogElement = await screen.findByRole("dialog", { name: "Settings" });
      await waitFor(() => expect(dialogElement).toBeVisible());
      const dialog = within(dialogElement);
      await expect(dialog.getByRole("combobox", { name: /^Theme / })).toHaveTextContent(
        /Auto|Light|Dark/,
      );
      await expect(dialog.getByText("Theme", { exact: true })).toBeVisible();
      await expect(
        dialog.getByRole("checkbox", { name: "Automatically rotate models" }),
      ).toBeVisible();
      await userEvent.click(dialog.getByRole("button", { name: "Close settings" }));
      await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
      await expect(trigger).toHaveFocus();
    });
  }}
/>
