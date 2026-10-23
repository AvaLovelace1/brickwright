<script lang="ts">
  import { tick } from "svelte";
  import { stageStyles, type Flow, type Stage } from "#lib/method.js";
  import PythonCode from "#lib/components/PythonCode.svelte";
  import Bullet from "#lib/components/Bullet.svelte";

  let { stage, flow }: { stage: Stage; flow?: Flow } = $props();
  const uid = $props.id();
  let viewport: HTMLDivElement;
  let viewportWidth = $state(0);
  const ROW_Y = 75;
  const EXPLORE_Y = 165;
  const RETURN_Y = 184;
  const REVISION_X = 460;
  const EXPLORE_WRITE_X = 330;
  const ARROW_GAP = 3;
  const layout = {
    input: { left: 0, width: 250 },
    write: { left: 280, width: 220 },
    validate: { left: 540, width: 235 },
    render: { left: 820, width: 120 },
    finalize: { left: 980, width: 120 },
    explore: { left: 20, width: 390 },
  };

  const rightX = (id: Stage) => layout[id].left + layout[id].width;
  const centerX = (id: Stage) => layout[id].left + Math.floor(layout[id].width / 2);
  const forward = (from: Stage, to: Stage) =>
    `M${rightX(from)} ${ROW_Y} H${layout[to].left - ARROW_GAP}`;

  const nodes: {
    id: Stage;
    title: string;
    icon: string;
    codeTitle?: boolean;
    description?: string | [label: string, text: string][];
    code?: string;
  }[] = [
    {
      id: "input",
      title: "Input",
      icon: "tdesign--chat-message",
      description: [
        ["User", "Text and/or image prompt"],
        ["System", "BrickLayer documentation; create-execute-validate instructions"],
      ],
    },
    {
      id: "write",
      title: "Write build.py",
      icon: "tdesign--code",
      code: "import bricklayer\ndef create_build(): …\ndef run_tests(): …",
    },
    {
      id: "validate",
      title: "validate()",
      codeTitle: true,
      icon: "tdesign--task-checked",
      description:
        "Compiles, no collisions or floaters, expected number of components, passes custom tests?",
    },
    {
      id: "render",
      title: "render()",
      codeTitle: true,
      icon: "tdesign--image",
      description: "Multi-view or custom view",
    },
    {
      id: "finalize",
      title: "finalize()",
      codeTitle: true,
      icon: "tdesign--check-circle",
      description: "Completed brick build",
    },
    {
      id: "explore",
      title: "explore(snippet)",
      codeTitle: true,
      icon: "tdesign--compass",
      description: "Optionally run a Python snippet to investigate BrickLayer",
    },
  ];

  // Initial estimates are replaced by measured content heights after mounting.
  let heights = $state<Record<Stage, number>>({
    input: 150,
    write: 120,
    validate: 150,
    render: 102,
    finalize: 102,
    explore: 102,
  });
  const writeArrowEnd = $derived(ROW_Y + heights.write / 2 + ARROW_GAP);
  const diagramHeight = $derived(EXPLORE_Y + heights.explore + 10);

  const edges: { id: Flow | "input-write" | "revise-explore"; path: string }[] = $derived([
    { id: "input-write", path: forward("input", "write") },
    { id: "write-validate", path: forward("write", "validate") },
    { id: "tests-pass", path: forward("validate", "render") },
    { id: "render-ok", path: forward("render", "finalize") },
    { id: "input-explore", path: `M${centerX("input")} ${ROW_Y} V${EXPLORE_Y - ARROW_GAP}` },
    { id: "explore-write", path: `M${EXPLORE_WRITE_X} ${EXPLORE_Y} V${writeArrowEnd}` },
    {
      id: "tests-fail",
      path: `M${centerX("validate")} ${ROW_Y} V${RETURN_Y} H${REVISION_X} V${writeArrowEnd}`,
    },
    {
      id: "render-revise",
      path: `M${centerX("render")} ${ROW_Y} V${RETURN_Y} H${REVISION_X} V${writeArrowEnd}`,
    },
    {
      id: "revise-explore",
      path: `M${centerX("validate")} ${RETURN_Y} H${REVISION_X} V${EXPLORE_Y + heights.explore / 2} H${rightX("explore") + ARROW_GAP}`,
    },
  ]);
  // Draw the active route last so shared segments retain the highlight color.
  const orderedEdges = $derived([
    ...edges.filter((edge) => edge.id !== flow),
    ...edges.filter((edge) => edge.id === flow),
  ]);

  $effect(() => {
    // Keep the highlighted node in the diagram's own viewport on small screens.
    // Scrolling this container never moves the surrounding page or chat.
    const active = stage;
    const width = viewportWidth;
    const element = viewport;
    let cancelled = false;
    void tick().then(() => {
      if (cancelled || !element) return;
      const node = element.querySelector<HTMLElement>(`[data-stage="${active}"]`);
      if (node)
        element.scrollTo({
          left: node.offsetLeft - Math.max(0, (width - node.offsetWidth) / 2),
          behavior: "instant",
        });
    });
    return () => {
      cancelled = true;
    };
  });
</script>

<p class="px-3 pt-3 text-right text-xs sm:px-4 xl:hidden">Scroll to view diagram →</p>
<!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard access to the horizontally scrollable diagram.) -->
<div
  bind:this={viewport}
  bind:clientWidth={viewportWidth}
  role="region"
  aria-label="Build creation flowchart"
  tabindex="0"
  class="overflow-x-auto overscroll-x-contain p-4 focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-line sm:p-6"
>
  <div
    style:--diagram-height={`${diagramHeight}px`}
    class="relative mx-auto h-(--diagram-height) w-275"
  >
    <svg
      class="pointer-events-none absolute inset-0 h-full w-full overflow-visible"
      viewBox={`0 0 1100 ${diagramHeight}`}
      aria-hidden="true"
    >
      <defs>
        <marker
          id="{uid}-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" class="fill-line" />
        </marker>
        <marker
          id="{uid}-active-arrow"
          viewBox="0 0 10 10"
          refX="9"
          refY="5"
          markerWidth="5"
          markerHeight="5"
          orient="auto-start-reverse"
        >
          <path d="M0 0 L10 5 L0 10 z" class="fill-link" />
        </marker>
      </defs>
      {#each orderedEdges as edge (edge.id)}
        <path
          d={edge.path}
          fill="none"
          stroke="currentColor"
          stroke-width={flow === edge.id ? 3 : 1.5}
          marker-end="url(#{uid}-{flow === edge.id ? 'active-arrow' : 'arrow'})"
          class={flow === edge.id ? "text-link" : "text-line"}
        />
      {/each}
      <g class="fill-success-deep font-body text-xs font-semibold dark:fill-success-bright">
        <text x="797" y="52" text-anchor="middle">Tests<tspan x="797" dy="12">pass</tspan></text>
        <text x="960" y="66" text-anchor="middle">OK</text>
      </g>
      <g class="fill-danger font-body text-xs font-semibold dark:fill-danger-brighter">
        <text x="667" y={ROW_Y + heights.validate / 2 + 18}>Tests fail</text>
        <text x="890" y={ROW_Y + heights.render / 2 + 18}>Not OK</text>
      </g>
    </svg>
    <ol aria-label="Flowchart stages">
      {#each nodes as node (node.id)}
        {@const colors = stageStyles[node.id]}
        <li
          bind:offsetHeight={heights[node.id]}
          data-stage={node.id}
          style:--node-left={`${layout[node.id].left}px`}
          style:--node-width={`${layout[node.id].width}px`}
          style:--node-top={`${node.id === "explore" ? EXPLORE_Y : ROW_Y}px`}
          aria-current={stage === node.id ? "step" : undefined}
          class={[
            "absolute top-(--node-top) left-(--node-left) w-(--node-width) rounded-(--bb-border-radius)",
            "border-2 border-t-4 p-3 transition-colors duration-200 motion-reduce:transition-none",
            node.id !== "explore" && "-translate-y-1/2",
            colors.topBorder,
            stage === node.id
              ? ["bg-surface ring-2 ring-offset-2 ring-offset-bg", colors.border, colors.ring]
              : "border-line bg-surface",
          ]}
        >
          <div class="mb-2 flex items-center gap-2 text-sm leading-tight font-semibold">
            <span class="iconify {node.icon} shrink-0 text-lg" aria-hidden="true"></span>
            {#if node.codeTitle}
              <code class="font-mono text-xs">{node.title}</code>
            {:else}<span>{node.title}</span>{/if}
          </div>
          {#if typeof node.description === "string"}
            <p class="text-sm leading-relaxed">{node.description}</p>
          {:else if node.description}
            {#each node.description as [label, text] (label)}
              <p class="text-sm leading-relaxed">
                <span class="italic">{label}</span><Bullet class="mx-1" />{text}
              </p>
            {/each}
          {/if}
          {#if node.code}<pre class="mt-3 font-mono text-xs leading-relaxed"><PythonCode
                code={node.code}
              /></pre>{/if}
          {#if stage === node.id}
            <span class={["absolute -top-3 right-2 px-1 text-xs font-semibold", colors.badge]}>
              Current step
            </span>
          {/if}
        </li>
      {/each}
    </ol>
    <p
      style:--label-top={`${RETURN_Y + 4}px`}
      style:--label-left={`${REVISION_X + 20}px`}
      class={[
        "absolute top-(--label-top) left-(--label-left) text-sm font-semibold",
        flow === "tests-fail" || flow === "render-revise"
          ? "text-link underline decoration-current decoration-2 underline-offset-3"
          : "",
      ]}
    >
      Inspect results &amp; revise
    </p>
  </div>
</div>
