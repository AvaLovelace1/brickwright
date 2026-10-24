<script lang="ts">
  import { createModel } from "#lib/models.js";
  import { agents } from "#lib/experiment-results.js";
  import ModelComparison from "./ModelComparison.svelte";

  let groups = $state(
    agents.toReversed().map((agent) => ({
      name: agent.label,
      models: (["without", "with"] as const).map((variant) => ({
        label: variant === "with" ? "BrickWright" : agent.baseline,
        ...createModel(
          `agent-comparison/spaceship-${agent.slug}-${variant}-brickwright`,
          `${agent.label} build ${variant} BrickWright`,
        ),
      })),
    })),
  );
</script>

<ModelComparison
  title="Better builds with BrickWright"
  prompt="This is a white and black LEGO spaceship with a blue tinted canopy, featuring a blue-suited minifigure pilot, rear thrusters, and side-mounted weapons."
  bind:groups
>
  {#snippet caption()}
    <strong>
      Given the same prompt, BrickWright-equipped agents produce higher-quality builds with fewer
      physical violations than agents using general tools.
    </strong>
    The improvement is especially striking for lightweight agents Luna and Haiku. All BrickWright builds
    use real LEGO® parts, with no colliding (intersecting) or floating parts and one connected component.
    Red lines indicate brick intersections. Drag a model to rotate it.
  {/snippet}
</ModelComparison>
