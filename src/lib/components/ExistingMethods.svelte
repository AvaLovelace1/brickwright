<script lang="ts">
  import { asset } from "$app/paths";
  import ModelDiagnosticControls from "./ModelDiagnosticControls.svelte";
  import ModelViewer, { type LegoModelView } from "./ModelViewer.svelte";
  import SharedCanvas from "./SharedCanvas.svelte";

  const uid = $props.id();
  const modelPath = "models/truck-417/truck";
  const methodGroups = [
    {
      name: "Specialized text-to-brick models",
      methods: [
        { name: "BrickGPT", run: "brickgpt" },
        { name: "BrickNet", run: "bricknet" },
      ],
    },
    {
      name: "Agentic methods",
      methods: [
        { name: "Codex (GPT-6 Astra)", run: "codex-astra-docs" },
        { name: "Codex (GPT-6.1 Sol)", run: "codex-sol-docs" },
      ],
    },
  ] as const;

  interface MethodModel extends LegoModelView {
    name: string;
  }

  let groups = $state(
    methodGroups.map((group) => ({
      name: group.name,
      models: group.methods.map(({ run, ...method }): MethodModel => ({
        ...method,
        ldr: asset(`${modelPath}-${run}.ldr`),
        ldrPacked: asset(`${modelPath}-${run}.packed.mpd`),
        diagnosticsUrl: asset(`${modelPath}-${run}.diagnostics.json`),
        caption: `${method.name} build`,
        maxSteps: 1,
        stepsShown: 1,
      })),
    })),
  );
  const models = $derived(groups.flatMap((group) => group.models));
  let showIntersections = $state(true);
  let highlightCollisions = $state(false);
</script>

<figure aria-labelledby="{uid}-title" aria-describedby="{uid}-caption" class="relative">
  <div class="mb-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
    <h3 id="{uid}-title" class="font-display text-2xl font-extrabold">Existing methods</h3>
    <ModelDiagnosticControls bind:showIntersections bind:highlightCollisions />
  </div>
  <p class="mb-6 text-sm text-pretty">
    <span class="font-bold">Prompt:</span>
    <span class="italic">
      “This is a blue and gray LEGO flatbed truck featuring a detailed cab, four wheels with
      fenders, and a large gray cylindrical object mounted on its black studded cargo bed.”
    </span>
  </p>
  <div class="grid grid-cols-1 gap-6 lg:grid-cols-2">
    {#each groups as group (group.name)}
      <div class="min-w-0">
        <h4 class="mb-3 border-b border-line pb-1 text-center font-display text-xl font-extrabold">
          {group.name}
        </h4>
        <div class="grid grid-cols-2 gap-3">
          {#each group.models as model, i (model.name)}
            <div class="min-w-0">
              <p class="mb-1 text-center font-semibold">{model.name}</p>
              <ModelViewer
                bind:model={group.models[i]}
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
      Agentic methods better capture the request, but still produce physically infeasible builds.
    </strong>
    Both Codex outputs contain colliding bricks. Red lines indicate brick intersections. Drag a model
    to rotate it.
  </figcaption>
</figure>
