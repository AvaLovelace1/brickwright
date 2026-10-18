<script lang="ts">
  import SectionDivider from "#lib/components/SectionDivider.svelte";
  import Overview from "#lib/sections/Overview.svelte";
  import Motivation from "#lib/sections/Motivation.svelte";
  import Method from "#lib/sections/Method.svelte";
  import Experiments from "#lib/sections/Experiments.svelte";
  import Acknowledgments from "#lib/sections/Acknowledgments.svelte";
  import Citation from "#lib/sections/Citation.svelte";
</script>

<svelte:head>
  <title>BrickWright: Agentic Creation of Physically Feasible Brick Builds</title>
</svelte:head>

<Overview />
<SectionDivider />
<Motivation />
<SectionDivider />
<Method />
<SectionDivider />
<Experiments />
<SectionDivider />
<Acknowledgments />
<SectionDivider />
<Citation />
