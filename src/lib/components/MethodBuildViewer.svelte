<script lang="ts">
  import { asset } from "$app/paths";
  import ModelViewer, { type LegoModelView } from "./ModelViewer.svelte";
  import ModelDiagnosticControls from "./ModelDiagnosticControls.svelte";
  import SharedCanvas from "./SharedCanvas.svelte";
  import PythonCode from "./PythonCode.svelte";
  import Tooltip from "./Tooltip.svelte";
  import { methodBuilds, type BuildRevision } from "#lib/method.js";

  let { revision }: { revision: BuildRevision | null } = $props();

  function createModel(revision: BuildRevision): LegoModelView {
    return {
      ldr: asset(`models/method/house-${revision}.ldr`),
      ldrPacked: asset(`models/method/house-${revision}.packed.mpd`),
      diagnosticsUrl: asset(`models/method/house-${revision}.diagnostics.json`),
      caption: "Current house build",
      stepsShown: 1,
      maxSteps: 1,
    };
  }

  // Retain each viewer's loaded state when moving between revisions.
  let models = $state({
    draft1: createModel("draft1"),
    draft2: createModel("draft2"),
    final: createModel("final"),
  });
  let highlightCollisions = $state(false);
  let showIntersections = $state(true);
</script>

{#snippet emptyState(label: string, icon: string)}
  <div class="flex h-full flex-col items-center justify-center gap-3 p-4 text-center">
    <span class="iconify {icon} text-3xl" aria-hidden="true"></span>
    <p class="text-sm font-semibold">{label}</p>
  </div>
{/snippet}

<aside
  aria-label="Current build and diagnostics"
  class="min-w-0 border-t-2 border-line bg-surface p-4 lg:border-t-0 lg:border-l-2"
>
  <p class="mb-3 text-sm font-semibold">Build so far</p>
  {#if revision}
    {#key revision}
      <div class="relative mb-4">
        <ModelViewer
          bind:model={models[revision]}
          class="h-64"
          showCaption={false}
          showBuildControls={false}
          {highlightCollisions}
          {showIntersections}
        />
        <SharedCanvas models={[models[revision]]} {highlightCollisions} {showIntersections} />
      </div>
    {/key}
    <ModelDiagnosticControls bind:highlightCollisions bind:showIntersections />
  {:else}
    <div class="h-64 bb-border bg-bg">
      {@render emptyState("No build yet", "tdesign--layers")}
    </div>
  {/if}
  <div class="mt-4 overflow-hidden bb-border bg-bg">
    <div
      class="flex items-center justify-between border-b-2 border-line bg-surface px-3 py-2 text-xs"
    >
      <span class="font-mono font-semibold">build.py</span>
      {#if revision}
        <Tooltip type={undefined}>
          {#snippet child({ props })}
            <a
              {...props}
              href={methodBuilds[revision].download}
              download="build.py"
              class="flex cursor-pointer items-center text-base text-text outline-link hover:text-link focus-visible:text-link focus-visible:outline-2"
            >
              <span class="iconify tdesign--download" aria-hidden="true"></span>
              <span class="sr-only">Download code</span>
            </a>
          {/snippet}
          {#snippet tooltipContent()}Download code{/snippet}
        </Tooltip>
      {/if}
    </div>
    {#if revision}
      <!-- svelte-ignore a11y_no_noninteractive_tabindex (Keyboard access to the scrollable source file.) -->
      <pre
        aria-label="Current build.py source"
        tabindex="0"
        class="h-48 overflow-auto p-3 font-mono text-xs leading-relaxed focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-line"><PythonCode
          code={methodBuilds[revision].source}
        /></pre>
    {:else}
      <div class="h-48">{@render emptyState("No file yet", "tdesign--file-1")}</div>
    {/if}
  </div>
</aside>
