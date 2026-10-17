<script lang="ts">
  import SectionDivider from "#lib/components/SectionDivider.svelte";
  import Overview from "#lib/sections/Overview.svelte";
  import Results from "#lib/sections/Results.svelte";
  import Acknowledgments from "#lib/sections/Acknowledgments.svelte";
  import Citation from "#lib/sections/Citation.svelte";
</script>

<svelte:head>
  <title>BrickWright: Agentic Creation of Physically Feasible Brick Builds</title>
</svelte:head>

<Overview />
<SectionDivider />
<Results />
<SectionDivider />
<Acknowledgments />
<SectionDivider />
<Citation />
