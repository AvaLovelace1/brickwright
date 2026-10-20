<script lang="ts">
  import { createModel } from "#lib/models.js";
  import { agents } from "#lib/experiment-results.js";
  import ModelDiagnosticControls from "#lib/components/ModelDiagnosticControls.svelte";
  import ModelViewer from "#lib/components/ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";

  const uid = $props.id();
  let pairs = $state(
    agents.toReversed().map((agent) => ({
      ...agent,
      models: ["without", "with"].map((variant) =>
        createModel(
          `agent-comparison/spaceship-${agent.slug}-${variant}-brickwright`,
          `${agent.label} build ${variant} BrickWright`,
        ),
      ),
    })),
  );
  const models = $derived(pairs.flatMap((pair) => pair.models));

  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
</script>

<figure aria-labelledby="{uid}-caption" class="relative">
  <div class="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
    <p class="font-display text-2xl font-extrabold">Better builds with BrickWright</p>
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
  </div>
  <p class="mb-6 text-sm text-pretty">
    <span class="font-bold">Prompt:</span>
    <span class="italic">
      “This is a white and black LEGO spaceship with a blue tinted canopy, featuring a blue-suited
      minifigure pilot, rear thrusters, and side-mounted weapons.”
    </span>
  </p>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    {#each pairs as pair (pair.value)}
      <div class="min-w-0">
        <p class="text-center font-display text-xl font-extrabold">{pair.label}</p>
        <div class="grid grid-cols-2 gap-3">
          {#each pair.models as model, side (model.ldr)}
            <div class="min-w-0">
              <p class="mb-1 text-center font-semibold">
                {side === 1 ? "BrickWright" : pair.baseline}
              </p>
              <ModelViewer
                bind:model={pair.models[side]}
                class="aspect-square"
                showCaption={false}
                {highlightCollisions}
                {showIntersections}
              />
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
  <SharedCanvas {models} {highlightCollisions} {showIntersections} />
  <figcaption id="{uid}-caption" class="mt-6 text-sm text-pretty">
    <strong>
      Given the same prompt, BrickWright-equipped agents produce higher-quality builds with fewer
      physical violations than agents using general tools.
    </strong>
    The improvement is especially striking for lightweight agents Luna and Haiku. All BrickWright builds
    use real LEGO® parts, with no colliding (intersecting) or floating parts and one connected component.
    Red lines indicate brick intersections. Drag a model to rotate it.
  </figcaption>
</figure>
