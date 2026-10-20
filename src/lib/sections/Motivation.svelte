<script lang="ts">
  import Container from "#lib/components/Container.svelte";
  import Prose from "#lib/components/Prose.svelte";
  import ExistingMethods from "#lib/content/ExistingMethods.svelte";
  import ExternalLink from "#lib/components/ExternalLink.svelte";
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
        generalize better than specialized text-to-brick methods, such as
        <ExternalLink href="https://avalovelace1.github.io/BrickGPT/">BrickGPT</ExternalLink>
        and <ExternalLink href="https://kulits.github.io/BrickNet/">BrickNet</ExternalLink>.
        However, agents still face challenges in creating <em>physically feasible</em> builds. Here we
        define a build to be physically feasible if it uses only real parts, has no colliding (intersecting)
        or floating parts, and forms a connected structure if possible.
      </p>
    </Prose>
  </Container>
  <Container class="mt-12 max-w-7xl">
    <ExistingMethods />
  </Container>
</section>
