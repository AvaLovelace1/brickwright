<script lang="ts">
  import BrickWrightLogo from "$lib/components/BrickWrightLogo.svelte";
  import Container from "$lib/components/Container.svelte";
  import type {LegoModelView} from "$lib/components/ModelViewer.svelte";
  import ModelViewer from "$lib/components/ModelViewer.svelte";
  import ldr from "$lib/assets/ldr/cruise-ship.ldr?url";
  import ldrPacked from "$lib/assets/ldr/cruise-ship.ldr_Packed.mpd?url";
  import SharedCanvas from "$lib/components/SharedCanvas.svelte";

  const AUTHORS = [
    { name: "Ava\u00A0Pun", aff: 1 },
    { name: "Kevin\u00A0Dai", aff: 1 },
    { name: "Sally\u00A0Chen", aff: 1 },
    { name: "Maxwell\u00A0Jones", aff: 1 },
    { name: "Ruixuan\u00A0Liu", aff: 1 },
    { name: "Kangle\u00A0Deng", aff: 2 },
    { name: "Changliu\u00A0Liu", aff: 1 },
    { name: "Maneesh\u00A0Agrawala", aff: 3 },
    { name: "Deva\u00A0Ramanan", aff: 1 },
    { name: "Jun\u2011Yan\u00A0Zhu", aff: 1 },
  ];
  const AFFILIATIONS = [
    "Carnegie\u00A0Mellon\u00A0University",
    "Roblox",
    "Stanford\u00A0University",
  ];
  const BULLET = " \u00A0▪\u00A0 ";

  let models = $state<LegoModelView[]>([
    { ldr, ldrPacked, caption: "A detailed LEGO cruise ship", maxBricks: 100, bricksShown: 1 },
    { ldr, ldrPacked, caption: "A detailed LEGO giraffe", maxBricks: 100, bricksShown: 1 },
    { ldr, ldrPacked, caption: "A city scene with four buildings", maxBricks: 100, bricksShown: 1 },
    { ldr, ldrPacked, caption: "model of my dog", maxBricks: 100, bricksShown: 1 },
  ]);
</script>

<svelte:head>
  <title>BrickWright: Agentic Creation of Physically Feasible Brick Builds</title>
</svelte:head>

<div class="flex justify-center border-b border-primary bg-text py-12 text-bg lg:py-16">
  <Container>
    <p class="mb-6 text-lg italic">Help me design…</p>
    <div class="mb-12 grid max-w-lg grid-cols-2 gap-4 lg:max-w-none lg:grid-cols-4">
      {#each models as model, i (model.caption)}
        <ModelViewer bind:model={models[i]} class="aspect-square" autoplay />
      {/each}
    </div>
    <span class="bb-badge bb-badge-primary mb-4 border-bg">Preprint 2026</span>
    <hgroup>
      <h1 class="mb-1 text-5xl sm:text-6xl">
        <BrickWrightLogo />
      </h1>
      <p class="mb-4 text-2xl font-semibold text-balance sm:text-3xl">
        Agentic Creation of Physically Feasible Brick Builds
      </p>
      <p class="mb-1 font-medium sm:text-lg">
        {#each AUTHORS as a, i (a.name)}
          <span>
            {a.name}&#8239;<sup class="font-normal">{a.aff}</sup>
            <span class="text-primary">{i < AUTHORS.length - 1 ? BULLET : ""}</span>
          </span>
        {/each}
      </p>
      <p class="text-sm">
        {#each AFFILIATIONS as aff, j (aff)}
          <span>
            <sup>{j + 1}</sup>&#8239;{aff}
            <span class="text-secondary">{j < AFFILIATIONS.length - 1 ? BULLET : ""}</span>
          </span>
        {/each}
      </p>
    </hgroup>
  </Container>
</div>
<div class="flex justify-center py-8 lg:py-12">
  <Container>
    <div class="prose prose-bb prose-ul:list-[square]">
      <p class="lead">
        placeholder text
      </p>
      <p>
        placeholder text
      </p>
    </div>
  </Container>
</div>

<SharedCanvas bind:models />
