<script lang="ts">
  import Container from "#lib/components/Container.svelte";
  import Prose from "#lib/components/Prose.svelte";
  import QualitativeResults from "#lib/components/QualitativeResults.svelte";
  import QuantitativeResults from "#lib/components/QuantitativeResults.svelte";
</script>

<section
  id="experiments"
  aria-labelledby="experiments-heading"
  class="flex flex-col items-center py-12"
>
  <Container>
    <Prose>
      <h2 id="experiments-heading">Experiments</h2>
      <p>
        We evaluate physical feasibility and prompt adherence on BrickNet-512, a dataset of 512 text
        prompts created by VLM captioning of human-made brick builds. As seen in the visual
        comparison below, BrickWright reduces colliding and floating artifacts for all agent
        backends and improves the coherence of builds created by lightweight agents.
      </p>
    </Prose>
  </Container>
  <Container class="my-12">
    <QualitativeResults />
  </Container>
  <Container>
    <Prose>
      <p>
        Numeric results are given in the table below. Compared to vanilla agent baselines, brick
        builds produced by BrickWright-equipped agents exhibit greatly improved physical feasibility
        with broadly comparable token costs. This increase in physical validity is not accompanied
        by a significant decrease in complexity or fidelity; on average, BrickWright agents create
        builds with more bricks than vanilla agent baselines, while improving prompt adherence for
        lightweight models (Haiku, Luna) and maintaining it for powerful models (Sol, Astra).
        BrickWright-equipped agents additionally outperform specially trained text-to-brick models
        in overall validity, connectivity, and prompt adherence. The Articraft baseline, which is
        intended for digital 3D assets and does not handle brick build-specific constraints, yields
        better prompt adherence but worse physical validity.
      </p>
    </Prose>
  </Container>
  <Container class="mt-12 max-w-7xl">
    <QuantitativeResults />
  </Container>
</section>
