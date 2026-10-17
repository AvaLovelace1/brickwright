<script lang="ts">
  import BrickWrightLogo from "#lib/components/BrickWrightLogo.svelte";
  import Container from "#lib/components/Container.svelte";
  import Teaser from "#lib/components/Teaser.svelte";
  import Prose from "#lib/components/Prose.svelte";

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
</script>

<section id="overview" aria-label="Overview">
  <div class="flex justify-center border-b border-primary bg-text py-12 text-bg lg:py-16">
    <Container>
      <Teaser />
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
      <Prose>
        <p class="lead">
          <strong>BrickWright</strong> enables pre-trained coding agents to generate high-fidelity,
          <em>physically feasible</em> LEGO® builds from text or image prompts. Its key idea:
        </p>
        <blockquote class="bb-callout bb-callout-primary lead">
          Give agents a <strong>programmatic toolkit</strong> for creating and validating brick builds.
        </blockquote>
        <p>
          <BrickWrightLogo class="not-prose text-lg" /> guides agents to generate brick builds by writing
          code with <BrickWrightLogo variant="layer" class="not-prose text-lg" />, a Python toolkit
          for brick build creation and validation. Agents guided by BrickWright produce
          higher-quality builds with fewer physical violations than agents with general tools.
          Additionally, they outperform specialized models on the text-to-brick task. BrickWright is
          especially useful for lightweight agents: on a sample of 512 prompts, it improves GPT-6
          Luna's performance from 11% to 100% physically valid builds while boosting prompt
          adherence, at 2% the price of frontier models. BrickWright works with any agent backend;
          <a href="https://github.com/AvaLovelace1/brickwright">code is available on GitHub.</a>
        </p>
      </Prose>
    </Container>
  </div>
</section>
