<script lang="ts">
  import { asset } from "$app/paths";
  import RadioGroup from "./RadioGroup.svelte";
  import ModelViewer, { type LegoModelView } from "./ModelViewer.svelte";
  import SharedCanvas from "./SharedCanvas.svelte";

  const uid = $props.id();
  const modelDirectory = "models/spaceship-309";
  const agents = [
    {
      name: "GPT-6 Astra",
      baseline: "spaceship-gpt-6-astra-without-brickwright",
      brickwright: "spaceship-gpt-6-astra-with-brickwright",
    },
    {
      name: "GPT-6.1 Sol",
      baseline: "spaceship-gpt-6-1-sol-without-brickwright",
      brickwright: "spaceship-gpt-6-1-sol-with-brickwright",
    },
    {
      name: "GPT-6 Luna",
      baseline: "spaceship-gpt-6-luna-without-brickwright",
      brickwright: "spaceship-gpt-6-luna-with-brickwright",
    },
    {
      name: "Claude Haiku 5.5",
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
      models: [agent.baseline, agent.brickwright].map((filename, side): ComparisonModel => ({
        filename,
        withBrickwright: side === 1,
        ldr: asset(`${modelDirectory}/${filename}.ldr`),
        ldrPacked: asset(`${modelDirectory}/${filename}.packed.mpd`),
        caption: `${agent.name} build ${side === 1 ? "with" : "without"} BrickWright`,
        maxBricks: 1,
        bricksShown: 1,
      })),
    })),
  );
  const models = $derived(pairs.flatMap((pair) => pair.models));

  let view = $state("intersections");
  const views = [
    { value: "normal", label: "Normal" },
    { value: "intersections", label: "Intersections" },
    { value: "invalid", label: "Invalid placements" },
  ];
</script>

<figure aria-labelledby="{uid}-caption" class="relative">
  <div class="mb-4 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
    <p class="font-display text-2xl font-extrabold">Better builds with BrickWright</p>
    <RadioGroup label="View" options={views} bind:value={view} />
  </div>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    {#each pairs as pair (pair.name)}
      <div class="min-w-0">
        <p class="text-center font-display text-lg font-extrabold">{pair.name}</p>
        <div class="grid grid-cols-2 gap-2">
          {#each pair.models as model, side (model.filename)}
            <div class="min-w-0">
              <p class="mb-1 text-center text-sm font-semibold">
                {model.withBrickwright ? "With BrickWright" : "Vanilla agent"}
              </p>
              <ModelViewer
                bind:model={pair.models[side]}
                class="aspect-square"
                showCaption={false}
                badge={{
                  text: model.withBrickwright ? "Valid" : "Collisions",
                  tone: model.withBrickwright ? "success" : "danger",
                }}
              />
            </div>
          {/each}
        </div>
      </div>
    {/each}
  </div>
  <SharedCanvas {models} />
  <figcaption id="{uid}-caption" class="mt-6 text-sm text-pretty">
    <strong>
      Given the same prompt, BrickWright-equipped agents produce higher-quality builds with fewer
      physical violations than agents using general tools.
    </strong>
    The improvement is especially striking for lightweight agents Luna and Haiku. Prompt: “This is a white
    and black LEGO spaceship with a blue tinted canopy, featuring a blue-suited minifigure pilot, rear
    thrusters, and side-mounted weapons.” All BrickWright builds use real LEGO® parts, with no colliding
    (intersecting) or floating parts and one connected component. Drag a model to rotate it.
  </figcaption>
</figure>
