<script lang="ts" module>
  import { Box3, EquirectangularReflectionMapping, Object3D, type Texture, Vector3 } from "three";
  import { LDrawLoader } from "three/examples/jsm/loaders/LDrawLoader.js";
  import { HDRLoader } from "three/examples/jsm/loaders/HDRLoader.js";
  import { LDrawConditionalLineMaterial } from "three/addons/materials/LDrawConditionalLineMaterial.js";
  import envMapUrl from "#lib/assets/studio_kontrast_02_1k.hdr?url";
  import { parsePackedModel } from "#lib/ldraw.js";

  // One LDrawLoader shared across all LegoModel instances.
  const loader = new LDrawLoader();
  loader.setConditionalLineMaterial(LDrawConditionalLineMaterial);
  let envMap: Promise<Texture> | undefined;
  const models: Record<string, Promise<Object3D>> = {};
  // Parse models one at a time with a gap in between, so the browser can handle other events in between
  let queue: Promise<unknown> = Promise.resolve();
  const yieldToBrowser = () => new Promise((resolve) => setTimeout(resolve));

  function loadEnvMap() {
    envMap ??= new HDRLoader().loadAsync(envMapUrl).then((texture) => {
      texture.mapping = EquirectangularReflectionMapping;
      return texture;
    });
    return envMap;
  }

  // Load an LDraw model, parsing each URL once. Clones share geometry and materials with the cached model.
  async function loadModel(url: string) {
    if (!models[url]) {
      models[url] = queue
        .then(async () => {
          const response = await fetch(url);
          if (!response.ok) throw new Error(`Unable to load model: ${response.status} ${url}`);
          return parsePackedModel(loader, await response.text());
        })
        .then(normalizeModel);
      queue = models[url].then(yieldToBrowser, yieldToBrowser);
    }
    return (await models[url]).clone();
  }

  // Normalize a model to the unit cube
  function normalizeModel(group: Object3D) {
    group.rotation.x = Math.PI;
    const box = new Box3().setFromObject(group);
    const scale = 2 / Math.max(...box.getSize(new Vector3()).toArray());
    group.scale.setScalar(scale);
    group.position.copy(box.getCenter(new Vector3())).multiplyScalar(-scale);
    return group;
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
  import type { LegoModelView } from "./ModelViewer.svelte";
  const { invalidate } = useThrelte();

  interface Props extends Partial<DiagnosticDisplay> {
    model: LegoModelView;
    onload: (maxSteps: number) => void;
    ondiagnosticerror: () => void;
  }
  let {
    model,
    onload,
    ondiagnosticerror,
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
      ondiagnosticerror();
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
    onload(group.children.length);
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
