<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect, screen, waitFor } from "storybook/test";
  import Select from "./Select.svelte";

  async function expectAnimationToFinish(element: HTMLElement) {
    // Svelte starts transitions on the next frame.
    await new Promise(requestAnimationFrame);
    const animations = element.getAnimations();
    await expect(animations.length).toBeGreaterThan(0);
    await Promise.all(animations.map((animation) => animation.finished));
  }

  const { Story } = defineMeta({
    title: "Components/Select",
    component: Select,
    tags: ["autodocs"],
    args: {
      label: "Model",
      options: [
        { value: "ship", label: "Cruise ship" },
        { value: "unavailable", label: "Unavailable model", disabled: true },
        { value: "giraffe", label: "Giraffe" },
      ],
    },
  });
</script>

<script lang="ts">
  let selected = $state("ship");
</script>

<Story
  name="Default"
  play={async ({ canvas, userEvent, step }) => {
    const trigger = canvas.getByRole("button", { name: "Model Cruise ship" });
    const boundValue = canvas.getByRole("status");
    for (const action of ["Select", "Reselect"]) {
      await step(`${action} an option without clearing the bound value`, async () => {
        await userEvent.click(trigger);
        await userEvent.click(await screen.findByRole("option", { name: "Giraffe" }));
        await waitFor(() => expect(screen.queryByRole("listbox")).toBeNull());
        await expect(trigger).toHaveAccessibleName("Model Giraffe");
        await expect(trigger).toHaveFocus();
        await expect(boundValue).toHaveTextContent("Selected: giraffe");
      });
    }
    await step("Opening and closing animations", async () => {
      for (let opening = 1; opening <= 2; opening++) {
        await userEvent.click(trigger);
        const menu = await screen.findByRole("listbox");
        await expectAnimationToFinish(menu);
        await expect(menu).toBeVisible();
        await userEvent.keyboard("{Escape}");
        await expectAnimationToFinish(menu);
        await waitFor(() => expect(menu).not.toBeInTheDocument());
      }
    });
  }}
>
  {#snippet template(args)}
    <Select {...args} bind:value={selected} />
    <p class="mt-2" role="status">Selected: {selected}</p>
  {/snippet}
</Story>

<Story
  name="Keyboard Selection"
  args={{ value: "ship", hideLabel: true }}
  play={async ({ canvas, userEvent }) => {
    const trigger = canvas.getByRole("button", { name: "Model Cruise ship" });
    trigger.focus();
    await userEvent.keyboard("{Enter}{ArrowDown}{Enter}");
    await expect(trigger).toHaveAccessibleName("Model Giraffe");
    await expect(trigger).toHaveFocus();
    await userEvent.keyboard("{Enter}{ArrowUp}{Escape}");
    await expect(trigger).toHaveAccessibleName("Model Giraffe");
    await expect(trigger).toHaveAttribute("aria-expanded", "false");
  }}
/>

<Story
  name="Placeholder"
  play={async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Model Select an option" })).toBeVisible();
  }}
/>

<Story
  name="Disabled"
  args={{ value: "ship", disabled: true }}
  play={async ({ canvas }) => {
    await expect(canvas.getByRole("button", { name: "Model Cruise ship" })).toBeDisabled();
  }}
/>

<Story
  name="Custom Label"
  args={{ value: "ship", labelClass: "shrink-0 text-base font-semibold", class: "min-w-0 flex-1" }}
  play={async ({ canvas }) => {
    const label = canvas.getByText("Model", { exact: true });
    const trigger = canvas.getByRole("button", { name: "Model Cruise ship" });
    await expect(label).toBeVisible();
    await expect(label).toHaveClass("shrink-0", "text-base", "font-semibold");
    await expect(trigger).toHaveClass("min-w-0", "flex-1");
    await expect(trigger).toHaveAccessibleName("Model Cruise ship");
  }}
>
  {#snippet template(args)}
    <div class="flex flex-col gap-2 sm:flex-row sm:items-center">
      <Select {...args} />
    </div>
  {/snippet}
</Story>
