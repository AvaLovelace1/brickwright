<script lang="ts">
  import Container from "#lib/components/Container.svelte";
  import Prose from "#lib/components/Prose.svelte";
  import BrickLayerCards from "#lib/content/BrickLayerCards.svelte";
  import MethodDemo from "#lib/content/MethodDemo.svelte";
</script>

<section id="method" aria-labelledby="method-heading" class="flex flex-col items-center py-12">
  <Container>
    <Prose>
      <h2 id="method-heading">Method</h2>
      <p>
        To help agents produce physically feasible builds, BrickWright equips them with a
        programmatic toolkit for brick build creation and validation. Following the paradigm of
        structure-as-code, it guides an agent to write Python code that produces a brick build using
        a custom package called BrickLayer. BrickLayer provides a unified programmatic
        representation for LEGO® build files, enabling them to be easily understood and edited by
        humans and agents. Key BrickLayer API components include the following:
      </p>
    </Prose>
  </Container>
  <Container class="my-12 max-w-7xl">
    <BrickLayerCards />
  </Container>
  <Container>
    <Prose>
      <p>
        To create a brick build from a text or image prompt, BrickWright provides a pre-trained
        agent with a set of tools—<code>validate</code>, <code>render</code>, and
        <code>finalize</code>—and prompts the agent to create a build with BrickLayer by writing and
        revising a single Python file in a plan-execute-validate loop. The <code>validate</code>
        tool provides feedback on the build’s physical feasibility, and the <code>render</code> tool
        allows the agent to inspect the build visually. When all feasibility tests pass and the
        agent is satisfied with the render, it calls <code>finalize</code>, completing the process.
      </p>
    </Prose>
  </Container>
  <Container class="mt-12 max-w-7xl">
    <MethodDemo />
  </Container>
</section>
