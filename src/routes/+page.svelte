<script lang="ts">
  import SectionDivider from "#lib/components/SectionDivider.svelte";
  import Overview, { AUTHORS } from "#lib/sections/Overview.svelte";
  import Motivation from "#lib/sections/Motivation.svelte";
  import Method from "#lib/sections/Method.svelte";
  import Experiments from "#lib/sections/Experiments.svelte";
  import Acknowledgments from "#lib/sections/Acknowledgments.svelte";
  import Citation from "#lib/sections/Citation.svelte";

  const SITE_URL = "https://avalovelace1.github.io/brickwright/";
  const TITLE = "BrickWright: Agentic Creation of Physically Feasible Brick Builds";
  const DESCRIPTION =
    "BrickWright enables pre-trained coding agents to generate high-fidelity, physically feasible LEGO® builds from text or image prompts.";
  const AUTHOR_NAMES = AUTHORS.map(({ name }) =>
    name.replace("\u00A0", " ").replace("\u2011", "-"),
  );
</script>

<svelte:head>
  <title>{TITLE}</title>
  <meta name="description" content={DESCRIPTION} />
  <meta name="author" content={AUTHOR_NAMES.join(", ")} />
  <link rel="canonical" href={SITE_URL} />
  <meta property="og:type" content="website" />
  <meta property="og:site_name" content="BrickWright" />
  <meta property="og:title" content={TITLE} />
  <meta property="og:description" content={DESCRIPTION} />
  <meta property="og:url" content={SITE_URL} />
  <meta property="og:image" content="{SITE_URL}og-image.png" />
  <meta property="og:image:width" content="1600" />
  <meta property="og:image:height" content="800" />
  <meta
    property="og:image:alt"
    content="A LEGO model built from a text prompt and checked for real parts, no collisions or floaters, and full connectivity."
  />
  <meta name="twitter:card" content="summary_large_image" />
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
