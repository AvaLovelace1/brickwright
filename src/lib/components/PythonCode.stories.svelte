<script module lang="ts">
  import { defineMeta } from "@storybook/addon-svelte-csf";
  import { expect } from "storybook/test";
  import PythonCode from "./PythonCode.svelte";

  const { Story } = defineMeta({
    title: "Components/PythonCode",
    component: PythonCode,
    tags: ["autodocs"],
  });
  const sample =
    'from bricklayer import Color\n\n# Build a house\ndef build():\n    count = 20\n    label = "\x3cscript>not HTML\x3c/script>"\n    return count\n';
</script>

<script lang="ts">
  let source = $state("roof_z = z + 2\n");
</script>

<Story
  name="Python"
  args={{ code: sample }}
  play={async ({ canvasElement }) => {
    const code = canvasElement.querySelector("code")!;
    await expect(code.textContent).toBe(sample);
    await expect(code.querySelector("script")).toBeNull();
    await expect(code.querySelector('[data-token="keyword"]')).toHaveTextContent("from");
    await expect(code.querySelector('[data-token="constant"]')).toHaveTextContent("20");
  }}
>
  {#snippet template(args)}
    <pre class="bb-border bg-bg p-4 text-sm"><PythonCode {...args} /></pre>
  {/snippet}
</Story>

<Story
  name="Updated Source"
  play={async ({ canvas, canvasElement, userEvent }) => {
    await userEvent.click(canvas.getByRole("button", { name: "Correct roof height" }));
    const code = canvasElement.querySelector("code")!;
    await expect(code.textContent).toBe("roof_z = z + 3\n");
    await expect(code.querySelector('[data-token="constant"]')).toHaveTextContent("3");
  }}
>
  {#snippet template()}
    <button class="bb-btn" onclick={() => (source = "roof_z = z + 3\n")}>Correct roof height</button
    >
    <pre class="mt-4 bb-border bg-bg p-4 text-sm"><PythonCode code={source} /></pre>
  {/snippet}
</Story>
