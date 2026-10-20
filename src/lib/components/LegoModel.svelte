<script lang="ts" module>
  import { EquirectangularReflectionMapping, type Object3D, type Texture } from "three";
  import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
  import envMapUrl from "#lib/assets/studio_kontrast_02_1k.hdr?url";
  import { loadModel } from "#lib/ldraw.js";
  let envMap: Promise<Texture> | undefined;

  function loadEnvMap() {
    envMap ??= new HDRLoader().loadAsync(envMapUrl).then((texture) => {
      texture.mapping = EquirectangularReflectionMapping;
      return texture;
    });
    return envMap;
  }
</script>

<script lang="ts">
  import { T, useThrelte } from "@threlte/core";
  import { Environment, OrbitControls, HTML } from "@threlte/extras";
  import { onMount } from "svelte";
  import {
    createDiagnosticView,
    type DiagnosticDisplay,
    type DiagnosticView,
  } from "#lib/model-diagnostics.js";
  import type { ModelView } from "#lib/models.js";
  const { invalidate } = useThrelte();

  interface Props extends Partial<DiagnosticDisplay> {
    model: ModelView;
  }
  let {
    model = $bindable(),
    highlightCollisions = false,
    showIntersections = false,
  }: Props = $props();
  let prevStepsShown = 0;
  let ldrawGroup = $state<Object3D>();
  let envMapTexture = $state<Texture>();
  let diagnosticView = $state<DiagnosticView>();

  function showSteps(group: Object3D) {
    const shown = Math.min(model.stepsShown, group.children.length);
    if (prevStepsShown < shown) {
      for (let i = prevStepsShown; i < shown; i++) {
        group.children[i].visible = true;
      }
    } else {
      for (let i = shown; i < prevStepsShown; i++) {
        group.children[i].visible = false;
      }
    }
    prevStepsShown = shown;
    invalidate();
  }

  $effect(() => {
    if (ldrawGroup) showSteps(ldrawGroup);
  });

  $effect(() => {
    if (!ldrawGroup || !model.diagnostics) return;
    try {
      const view = createDiagnosticView(ldrawGroup, model.diagnostics);
      diagnosticView = view;
      return () => {
        diagnosticView = undefined;
        view.dispose();
      };
    } catch {
      model.diagnosticsError = true;
    }
  });

  $effect(() => {
    if (!diagnosticView || !ldrawGroup) return;
    diagnosticView.update({
      highlightCollisions,
      // The exported lines describe the complete assembly, not individual build steps.
      showIntersections: showIntersections && model.stepsShown >= model.maxSteps,
    });
    invalidate();
  });

  onMount(async () => {
    loadEnvMap().then((texture) => (envMapTexture = texture));
    const group = await loadModel(model.ldrPacked);
    // A step reveals one top-level object: a part or an entire submodel.
    prevStepsShown = group.children.length;
    ldrawGroup = group;
    model.maxSteps = group.children.length;
    model.loaded = true;
  });

  let autoRotate = $state(true);
</script>

<T.PerspectiveCamera makeDefault position={[3, 0, 3]} fov={35}>
  <OrbitControls enableDamping {autoRotate} onstart={() => (autoRotate = false)} />
</T.PerspectiveCamera>
<Environment texture={envMapTexture} />
{#if !ldrawGroup}
  <HTML center><div class="text-sm text-text italic">Loading model…</div></HTML>
{/if}
<T is={ldrawGroup} />
{#if diagnosticView}<T is={diagnosticView.intersections} />{/if}
