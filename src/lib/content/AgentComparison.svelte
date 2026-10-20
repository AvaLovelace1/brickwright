<script lang="ts">
  import { asset } from "$app/paths";
  import ModelDiagnosticControls from "#lib/components/ModelDiagnosticControls.svelte";
  import ModelViewer, { type LegoModelView } from "#lib/components/ModelViewer.svelte";
  import SharedCanvas from "#lib/components/SharedCanvas.svelte";

  const uid = $props.id();
  const modelDirectory = "models/agent-comparison";
  const agents = [
    {
      name: "GPT-6 Astra",
      baselineAgent: "Codex",
      baseline: "spaceship-gpt-6-astra-without-brickwright",
      brickwright: "spaceship-gpt-6-astra-with-brickwright",
    },
    {
      name: "GPT-6.1 Sol",
      baselineAgent: "Codex",
      baseline: "spaceship-gpt-6-1-sol-without-brickwright",
      brickwright: "spaceship-gpt-6-1-sol-with-brickwright",
    },
    {
      name: "GPT-6 Luna",
      baselineAgent: "Codex",
      baseline: "spaceship-gpt-6-luna-without-brickwright",
      brickwright: "spaceship-gpt-6-luna-with-brickwright",
    },
    {
      name: "Claude Haiku 5.5",
      baselineAgent: "Claude Code",
      baseline: "spaceship-claude-haiku-5-5-without-brickwright",
      brickwright: "spaceship-claude-haiku-5-5-with-brickwright",
    },
  ] as const;
  interface ComparisonModel extends LegoModelView {
    filename: string;
    withBrickwright: boolean;
  }

  let pairs = $state(
    agents.map((agent) => ({
      name: agent.name,
      baselineAgent: agent.baselineAgent,
      models: [agent.baseline, agent.brickwright].map((filename, side): ComparisonModel => ({
        filename,
        withBrickwright: side === 1,
        ldr: asset(`${modelDirectory}/${filename}.ldr`),
        ldrPacked: asset(`${modelDirectory}/${filename}.packed.mpd`),
        diagnosticsUrl: asset(`${modelDirectory}/${filename}.diagnostics.json`),
        caption: `${agent.name} build ${side === 1 ? "with" : "without"} BrickWright`,
        maxSteps: 1,
        stepsShown: 1,
      })),
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
    {#each pairs as pair (pair.name)}
      <div class="min-w-0">
        <p class="text-center font-display text-xl font-extrabold">{pair.name}</p>
        <div class="grid grid-cols-2 gap-3">
          {#each pair.models as model, side (model.filename)}
            <div class="min-w-0">
              <p class="mb-1 text-center font-semibold">
                {model.withBrickwright ? "BrickWright" : pair.baselineAgent}
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
