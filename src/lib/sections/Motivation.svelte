<script lang="ts">
  import Container from "#lib/components/Container.svelte";
  import Prose from "#lib/components/Prose.svelte";
  import ExistingMethods from "#lib/components/ExistingMethods.svelte";
</script>

<section
  id="motivation"
  aria-labelledby="motivation-heading"
  class="flex flex-col items-center py-12"
>
  <Container>
    <Prose>
      <h2 id="motivation-heading">Motivation</h2>
      <p>
        Frontier coding agents like GPT-6 Astra are becoming increasingly adept at modeling 3D
        objects, including brick builds. Agentic methods produce higher-fidelity builds and
        generalize better than specialized text-to-brick methods, such as BrickGPT and BrickNet
        [cite these in a footnote]. However, agents still face challenges in creating
        <em>physically feasible</em> builds, often producing assemblies with floating parts, colliding
        (intersecting) parts, or many disconnected components.
      </p>
    </Prose>
  </Container>
  <Container class="mt-12 max-w-7xl">
    <ExistingMethods />
  </Container>
</section>
