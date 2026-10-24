<script lang="ts">
  import { createModel } from "#lib/models.js";
  import ModelComparison from "./ModelComparison.svelte";

  const method = (label: string, run: string) => ({
    label,
    ...createModel(`existing-methods/truck-${run}`, `${label} build`),
  });
  let groups = $state([
    {
      name: "Specialized text-to-brick models",
      models: [method("BrickGPT", "brickgpt"), method("BrickNet", "bricknet")],
    },
    {
      name: "Agentic methods",
      models: [
        method("Codex (GPT-6 Astra)", "codex-astra-docs"),
        method("Codex (GPT-6.1 Sol)", "codex-sol-docs"),
      ],
    },
  ]);
</script>

<ModelComparison
  title="Existing methods"
  prompt="This is a blue and gray LEGO flatbed truck featuring a detailed cab, four wheels with fenders, and a large gray cylindrical object mounted on its black studded cargo bed."
  bind:groups
>
  {#snippet caption()}
    <strong>
      Agentic methods better capture the request, but still produce physically infeasible builds.
    </strong>
    Both Codex outputs contain colliding bricks. Red lines indicate brick intersections. Drag a model
    to rotate it.
  {/snippet}
</ModelComparison>
