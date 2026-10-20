<script lang="ts">
  import PythonCode from "#lib/components/PythonCode.svelte";
  const cards = [
    {
      title: "Discover parts",
      icon: "tdesign--search",
      description:
        "Search the part catalog by keyword. Keywords may target specified metadata fields, such as category and dimensions. You may also filter by specifying a field’s exact value.",
      code: "search_parts(keywords, fields, filters)",
    },
    {
      title: "Assemble geometry",
      icon: "tdesign--layers",
      description:
        "Compose parts and sub-builds. Components may be placed with an exact pose or by automatically aligning typed connectors.",
      code: "b = LegoBuild()\np = Element(ldraw_id, color)\nb.add(p, position, rotation, relative_to, name, …)\nb.connect(p1, p1.find_connector(…), p2.find_connector(…))",
    },
    {
      title: "Check physical feasibility",
      icon: "tdesign--fact-check",
      description: "Find collisions, floating parts, and connected components.",
      code: "b.colliding_placements()\nb.floating_placements()\nb.connected_components()",
    },
  ];
</script>

<div
  class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.5fr)_minmax(0,1fr)]"
  aria-label="BrickLayer SDK functions"
>
  {#each cards as card (card.title)}
    <article class="bb-card flex min-w-0 flex-col gap-4">
      <h3 class="flex items-start gap-3 font-body text-lg leading-tight font-semibold">
        <span class="iconify {card.icon} shrink-0 text-xl" aria-hidden="true"></span>
        {card.title}
      </h3>
      <p class="text-sm leading-relaxed">{card.description}</p>
      <pre
        class="min-w-0 border-t-2 border-line pt-4 font-mono text-xs leading-relaxed wrap-break-word whitespace-pre-wrap"><PythonCode
          code={card.code}
        /></pre>
    </article>
  {/each}
</div>
